"""Bounded conversational orchestration around the existing JD workflow, not a new graph."""

import asyncio
import json
import re
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import ValidationError
from app.agents.jd.workflow import JobDescriptionWorkflow, get_job_description_workflow
from app.integrations.llm.recruiter_chat import RecruiterConversationContext, RecruiterInstructionInterpreter
from app.schemas.job_description import JobDescriptionGenerationRequest
from app.services.batch_screening import screening_suggestions
from app.schemas.recruiter_chat import (
    ClarificationResponse, DraftUnchangedResponse, FIELD_LABELS, JobDescriptionChatResponse, ScreeningSuggestionSource,
    RecruiterChatRequest, RecruiterChatResponse, UnsupportedResponse, PublishingContext,
)

ALIASES = {
    "employment_type": {"full_time": ("full time", "full-time", "fulltime"),
        "part_time": ("part time", "part-time", "parttime"),
        "contract": ("contract",), "temporary": ("temporary",), "internship": ("internship",)},
    "work_arrangement": {"remote": ("remote", "work from home", "wfh"),
        "on_site": ("on site", "on-site", "onsite"), "hybrid": ("hybrid",)},
}
NEGATION = re.compile(r"\b(?:no|not|without|never|exclude|excluding|maybe|possibly|don['\u2019]t|doesn['\u2019]t|isn['\u2019]t|aren['\u2019]t)\b", re.I)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def spans(phrase: str, text: str):
    return list(re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def has_conflicting_experience_minimum(message: str) -> bool:
    duration = r"\b(?:\d+|one|a|two|three|four|five|six|seven|eight|nine|ten)\s*\+?\s*years?\b"
    for clause in re.split(r"[.!?;]", normalized(message)):
        mandatory = re.search(r"\b(?:at least|minimum(?: of)?|require(?:d|s)?|must have|need(?:s)? to have)\b", clause)
        if (mandatory and re.search(duration, clause) and re.search(r"\bexperience\b", clause)
                and not re.search(r"\b(?:preferred|preferably|optional|desired)\b", clause)):
            return True
    return False


def prose_evidence_variants(field: str, evidence: str) -> set[str]:
    """Finite grammar changes, not fuzzy matching or model-supplied paraphrases."""
    variants = {evidence}
    if field not in {"role_summary", "responsibilities"}:
        return variants
    prefix = r"^(?:for a team |responsibilities include )"
    clause = re.sub(prefix, "", evidence)
    variants.add(clause)
    verbs = {"building": "build", "writing": "write", "working": "work"}
    first, separator, remainder = clause.partition(" ")
    if first in verbs and separator:
        variants.add(verbs[first] + " " + remainder)
    return variants


def grounded_value(field: str, item, message: str, *, pending_experience: bool = False):
    """Verify copied spans, conservative clause polarity and narrow normalization.

    Conflicting/negated occurrences clarify rather than selecting convenient evidence.
    Sentence boundaries exclude decimal dots, so version numbers remain intact.
    """
    evidence = normalized(item.evidence)
    text = normalized(message)
    matches = spans(evidence, text)
    if not matches:
        raise ValueError("Unsupported evidence.")
    if field == "minimum_experience_years" and item.value == 0:
        allowed = ("no minimum", "no minimum experience", "no minimum years", "no experience required",
                   "no experience is required", "no prior experience", "experience is not required",
                   "experience not required", "no experience necessary", "any experience level")
        if not any(spans(alias, evidence) for alias in allowed) or has_conflicting_experience_minimum(text):
            raise ValueError("No-minimum experience needs explicit evidence.")
        return 0
    for match in matches:
        left = re.split(r"[;!?]|(?<!\d)\.(?!\d)", text[:match.start()])[-1]
        right = re.split(r"[;!?]|(?<!\d)\.(?!\d)", text[match.end():])[0]
        clause = left + evidence + right
        if NEGATION.search(clause) or (field in {"required_skills", "responsibilities"} and re.search(r"\boptional\b", clause)):
            raise ValueError("Negated or ambiguous evidence.")
    if field == "minimum_experience_years":
        number_words = {"one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        durations = list(re.finditer(r"\b(\d+|one|a|two|three|four|five|six|seven|eight|nine|ten)\s*\+?\s*years?\b", evidence))
        if (len(durations) != 1 or re.search(r"\d+\.\d+\s*years?\b", evidence)
                or re.search(r"\d+\s*(?:-|to|\u2013)\s*\d+", evidence)):
            raise ValueError("Experience must have unambiguous experience evidence.")
        duration = durations[0]
        extracted_years = int(duration.group(1)) if duration.group(1).isdigit() else number_words[duration.group(1)]
        if extracted_years != item.value:
            raise ValueError("Experience value does not match its evidence.")
        if not re.search(r"\bexperience\b", evidence) and not pending_experience:
            raise ValueError("Experience evidence needs an explicit experience context.")
        return item.value
    value = normalized(item.value).rstrip(" .;:")
    if field in ALIASES:
        choices = {canonical for canonical, aliases in ALIASES[field].items()
                   if any(spans(alias, evidence) for alias in aliases)}
        if len(choices) != 1:
            raise ValueError("Ambiguous enum evidence.")
        canonical = choices.pop()
        if value not in (*ALIASES[field][canonical], canonical):
            raise ValueError("Unsupported enum value.")
        return canonical
    if not any(spans(value, variant) for variant in prose_evidence_variants(field, evidence.rstrip(" .;:"))):
        raise ValueError("Value not supported by evidence.")
    # Preserve source-backed values; only finite grammar/whitespace changes pass.
    return " ".join(unicodedata.normalize("NFC", item.value).split()).rstrip(" .;:")


@dataclass
class _GroundedItem:
    value: object
    evidence: str


@dataclass
class _Conversation:
    conversation_id: UUID
    created_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    messages: list[str] = field(default_factory=list)
    total_characters: int = 0
    requirements: dict[str, list[_GroundedItem]] = field(default_factory=dict)
    uncertain_fields: set[str] = field(default_factory=set)
    last_asked_field: str | None = None
    last_generated_requirements: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConversationUnavailableError(ValueError):
    """The server-held bounded conversation expired or reached its limits."""


class ConversationStore:
    """Short-lived in-memory state; sessions are neither durable nor shared across workers."""

    MAX_SESSIONS = 100
    TTL_SECONDS = 30 * 60
    MAX_TURNS = 20
    MAX_CHARACTERS = 12_000

    def __init__(self) -> None:
        self._sessions: OrderedDict[UUID, _Conversation] = OrderedDict()

    def get_or_create(self, conversation_id: UUID | None) -> _Conversation:
        now = time.monotonic()
        for key, item in list(self._sessions.items()):
            if not item.lock.locked() and now - item.last_seen > self.TTL_SECONDS:
                self._sessions.pop(key, None)
        if conversation_id is None:
            while len(self._sessions) >= self.MAX_SESSIONS:
                evictable = next((key for key, item in self._sessions.items() if not item.lock.locked()), None)
                if evictable is None:
                    raise ConversationUnavailableError
                self._sessions.pop(evictable, None)
            item = _Conversation(conversation_id=uuid4())
            self._sessions[item.conversation_id] = item
            return item
        item = self._sessions.get(conversation_id)
        if item is None:
            raise ConversationUnavailableError
        item.last_seen = now
        self._sessions.move_to_end(conversation_id)
        return item

    def add_message(self, session: _Conversation, message: str) -> None:
        if len(session.messages) >= self.MAX_TURNS or session.total_characters + len(message) > self.MAX_CHARACTERS:
            self._sessions.pop(session.conversation_id, None)
            raise ConversationUnavailableError
        session.messages.append(message)
        session.total_characters += len(message)
        session.last_seen = time.monotonic()

    def discard(self, session: _Conversation) -> None:
        self._sessions.pop(session.conversation_id, None)


_SHARED_CONVERSATIONS = ConversationStore()


REQUIRED_FIELDS = ("job_title", "role_summary", "responsibilities", "required_skills", "minimum_experience_years")
LIST_FIELDS = {"responsibilities", "required_skills", "preferred_skills", "education_requirements"}
FIELD_QUESTIONS = {
    "job_title": "What job title should I use?",
    "role_summary": "What will this person mainly work on?",
    "responsibilities": "What are the main responsibilities?",
    "required_skills": "Which technical skills are required?",
    "minimum_experience_years": "What minimum experience should candidates have, or is no minimum required?",
}
CORRECTION = re.compile(r"\b(?:actually|instead|rather than|replace|correct|change .{1,60} to|should be|no longer)\b", re.I)
class RecruiterChatService:
    def __init__(self, interpreter: RecruiterInstructionInterpreter, *,
        workflow_factory: Callable[[], JobDescriptionWorkflow] = get_job_description_workflow,
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._interpreter = interpreter
        self._workflow_factory = workflow_factory
        self._conversations = conversation_store or _SHARED_CONVERSATIONS

    async def respond(self, request: RecruiterChatRequest) -> RecruiterChatResponse:
        session = self._conversations.get_or_create(request.conversation_id)
        async with session.lock:
            if len(session.messages) >= self._conversations.MAX_TURNS or session.total_characters + len(request.message) > self._conversations.MAX_CHARACTERS:
                self._conversations.discard(session)
                raise ConversationUnavailableError
            posting = re.search(r"^(?:please\s+)?(?:(?:can|could|would) you\s+|(?:i want|i would like|i need) to\s+)?(?:publish|post|share)\b|\b(?:and|then)\s+(?:publish|post)\b", request.message, re.I)
            if posting and re.search(r"\b(?:jd|job|draft|description|discord|linkedin)\b", request.message, re.I):
                self._conversations.add_message(session, request.message)
                return UnsupportedResponse(conversation_id=session.conversation_id,
                    assistant_message="Job posting by chat instruction is not available. Review the draft and use its explicit Publish to Discord action.")
            context = self._provider_context(session)
            interpretation = await self._interpreter.interpret(request, context)
            if interpretation.intent == "unsupported":
                self._conversations.add_message(session, request.message)
                return UnsupportedResponse(conversation_id=session.conversation_id,
                    assistant_message="I can help gather job requirements and create a job-description draft. What job requirement would you like to work on?")
            requirements = interpretation.requirements
            updated_fields: set[str] = set()
            if requirements is not None:
                updated_fields = self._merge_requirements(session, requirements, request.message)
            self._conversations.add_message(session, request.message)
            missing = [name for name in REQUIRED_FIELDS if name in session.uncertain_fields or not session.requirements.get(name)]
            missing.extend(name for name in FIELD_LABELS if name in session.uncertain_fields and name not in missing)
            if missing:
                field_name = missing[0]
                session.last_asked_field = field_name
                if field_name in session.uncertain_fields:
                    assistant_message = f"I heard conflicting or unclear information about {FIELD_LABELS[field_name]}. Please state the final requirement clearly."
                else:
                    assistant_message = self._clarification_message(session, field_name, updated_fields)
                return ClarificationResponse(conversation_id=session.conversation_id, missing_fields=[field_name],
                    assistant_message=assistant_message)
            data = self._job_request_data(session)
            try:
                jd_request = JobDescriptionGenerationRequest.model_validate(data)
            except ValidationError as error:
                field_name = next((str(e["loc"][0]) for e in error.errors() if e["loc"]), "required_skills")
                if field_name not in FIELD_LABELS:
                    field_name = "required_skills"
                session.uncertain_fields.add(field_name)
                session.last_asked_field = field_name
                return ClarificationResponse(conversation_id=session.conversation_id, missing_fields=[field_name],
                    assistant_message=self._clarification_message(session, field_name, updated_fields))
            signature = json.dumps(jd_request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            if signature == session.last_generated_requirements:
                return DraftUnchangedResponse(conversation_id=session.conversation_id)
            result = await self._workflow_factory().generate(jd_request)
            suggestions = screening_suggestions(jd_request)
            sources = self._suggestion_sources(session, suggestions)
            session.last_asked_field = None
            session.last_generated_requirements = signature
            return JobDescriptionChatResponse(conversation_id=session.conversation_id, job_description_result=result,
                screening_suggestions=suggestions, screening_suggestion_sources=sources, publishing_context=PublishingContext(
                location=jd_request.location, employment_type=jd_request.employment_type, work_arrangement=jd_request.work_arrangement))

    def _provider_context(self, session: _Conversation) -> RecruiterConversationContext:
        prior = {name: [{"value": item.value, "evidence": item.evidence} for item in items]
                 for name, items in session.requirements.items()}
        return RecruiterConversationContext(tuple(session.messages[-8:]), prior, session.last_asked_field)

    def _merge_requirements(self, session: _Conversation, requirements, message: str) -> set[str]:
        pending_experience = session.last_asked_field == "minimum_experience_years"
        updated_fields: set[str] = set()
        for name in FIELD_LABELS:
            extracted = getattr(requirements, name, None)
            if not extracted:
                continue
            items = extracted if isinstance(extracted, list) else [extracted]
            validated: list[_GroundedItem] = []
            invalid = False
            for item in items:
                try:
                    value = grounded_value(name, item, message, pending_experience=pending_experience)
                    validated.append(_GroundedItem(value=value, evidence=item.evidence))
                except ValueError:
                    # A previously grounded value may be repeated by a provider; reuse only an exact server-held pair.
                    previous = session.requirements.get(name, [])
                    if any(old.value == item.value and normalized(old.evidence) == normalized(item.evidence) for old in previous):
                        continue
                    invalid = True
                    break
            if invalid:
                session.uncertain_fields.add(name)
                continue
            if not validated:
                continue
            old = session.requirements.get(name, [])
            correcting = bool(CORRECTION.search(message)) or (
                name == "minimum_experience_years" and any(item.value == 0 for item in validated)
            )
            if name in LIST_FIELDS:
                # A clearly additive correction ("also add Docker") must not
                # erase previously grounded list items just because it says
                # "actually". Evidence without an additive marker continues
                # to follow the existing replacement behavior.
                additive = re.search(r"\b(?:also|add|additionally|include|too|as well)\b", normalized(message))
                if additive:
                    correcting = False
                merged = [] if correcting else list(old)
                seen = {normalized(str(item.value)) for item in merged}
                for item in validated:
                    key = normalized(str(item.value))
                    if key not in seen:
                        merged.append(item)
                        seen.add(key)
                session.requirements[name] = merged
            else:
                new = validated[-1]
                if old and normalized(str(old[-1].value)) != normalized(str(new.value)) and not correcting:
                    session.uncertain_fields.add(name)
                    continue
                session.requirements[name] = [new]
            session.uncertain_fields.discard(name)
            updated_fields.add(name)
        return updated_fields

    def _job_request_data(self, session: _Conversation) -> dict[str, object]:
        data: dict[str, object] = {}
        for name in FIELD_LABELS:
            items = session.requirements.get(name, [])
            if name in LIST_FIELDS:
                data[name] = [item.value for item in items]
            else:
                data[name] = items[-1].value if items else None
        return data

    def _clarification_message(self, session: _Conversation, field_name: str, updated_fields: set[str] | None = None) -> str:
        title = session.requirements.get("job_title", [])
        updated_fields = updated_fields or set()
        if "job_title" in updated_fields and title:
            acknowledgement = f"Got it — {title[-1].value}. "
        elif updated_fields:
            latest = next(name for name in FIELD_LABELS if name in updated_fields)
            acknowledgement = f"Thanks — I’ve noted the {FIELD_LABELS[latest]}. "
        else:
            acknowledgement = ""
        question = FIELD_QUESTIONS.get(field_name, f"What {FIELD_LABELS[field_name].lower()} should I use?")
        return acknowledgement + question

    def _suggestion_sources(self, session: _Conversation, suggestions) -> list[ScreeningSuggestionSource]:
        evidence_by_value: dict[tuple[str, str], str] = {}
        for name in ("required_skills", "preferred_skills", "education_requirements"):
            for item in session.requirements.get(name, []):
                evidence_by_value[(name, normalized(str(item.value)))] = item.evidence
        for item in session.requirements.get("minimum_experience_years", []):
            if item.value != 0:
                evidence_by_value[("minimum_experience_years", normalized(str(item.value)))] = item.evidence
        results: list[ScreeningSuggestionSource] = []
        for criterion in suggestions.criteria:
            if criterion.category == "education":
                candidates = [evidence_by_value.get(("education_requirements", normalized(criterion.description)))]
            elif criterion.category == "experience":
                candidates = [item.evidence for item in session.requirements.get("minimum_experience_years", [])
                              if item.value != 0 and criterion.description == f"Minimum {item.value} years of relevant experience"]
            else:
                candidates = [evidence_by_value.get((field_name, normalized(criterion.description)))
                              for field_name in ("required_skills", "preferred_skills")]
            evidence = next((value for value in candidates if value), None)
            if evidence:
                results.append(ScreeningSuggestionSource(criterion_id=criterion.criterion_id, evidence=evidence))
        return results
