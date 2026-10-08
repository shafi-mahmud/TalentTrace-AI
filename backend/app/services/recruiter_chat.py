"""Single-turn orchestration around the existing JD workflow, not a new graph."""

import re
import unicodedata
from collections.abc import Callable

from pydantic import ValidationError
from app.agents.jd.workflow import JobDescriptionWorkflow, get_job_description_workflow
from app.integrations.llm.recruiter_chat import RecruiterInstructionInterpreter
from app.schemas.job_description import JobDescriptionGenerationRequest
from app.services.batch_screening import screening_suggestions
from app.schemas.recruiter_chat import (
    ClarificationResponse, FIELD_LABELS, JobDescriptionChatResponse,
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


def grounded_value(field: str, item, message: str):
    """Verify copied spans, conservative clause polarity and narrow normalization.

    Conflicting/negated occurrences clarify rather than selecting convenient evidence.
    Sentence boundaries exclude decimal dots, so version numbers remain intact.
    """
    evidence = normalized(item.evidence)
    text = normalized(message)
    matches = spans(evidence, text)
    if not matches:
        raise ValueError("Unsupported evidence.")
    for match in matches:
        left = re.split(r"[;!?]|(?<!\d)\.(?!\d)", text[:match.start()])[-1]
        right = re.split(r"[;!?]|(?<!\d)\.(?!\d)", text[match.end():])[0]
        clause = left + evidence + right
        if NEGATION.search(clause) or (field in {"required_skills", "responsibilities"} and re.search(r"\boptional\b", clause)):
            raise ValueError("Negated or ambiguous evidence.")
    if field == "minimum_experience_years":
        counts = re.findall(r"(?<![\w.+-])(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:[a-z-]+\s+){0,3}experience\b", evidence)
        if counts != [str(item.value)] or re.search(r"\d+\s*(?:-|to|\u2013)\s*\d+", evidence):
            raise ValueError("Experience must have unambiguous experience evidence.")
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


class RecruiterChatService:
    def __init__(self, interpreter: RecruiterInstructionInterpreter, *,
        workflow_factory: Callable[[], JobDescriptionWorkflow] = get_job_description_workflow,
    ) -> None:
        self._interpreter = interpreter
        self._workflow_factory = workflow_factory

    async def respond(self, request: RecruiterChatRequest) -> RecruiterChatResponse:
        # Recognize direct posting requests without any provider or publication call.
        posting = re.search(r"^(?:please\s+)?(?:(?:can|could|would) you\s+|(?:i want|i would like|i need) to\s+)?(?:publish|post|share)\b|\b(?:and|then)\s+(?:publish|post)\b", request.message, re.I)
        if posting and re.search(r"\b(?:jd|job|draft|description|discord|linkedin)\b", request.message, re.I):
            return UnsupportedResponse(assistant_message="Job posting by chat instruction is not available. Review a draft and use its Publish to Discord button.")
        interpretation = await self._interpreter.interpret(request)
        if interpretation.intent == "unsupported":
            return UnsupportedResponse()
        data, uncertain = {}, []
        requirements = interpretation.requirements
        for field in FIELD_LABELS:
            extracted = getattr(requirements, field, None) if requirements else None
            try:
                if isinstance(extracted, list):
                    data[field] = [grounded_value(field, item, request.message) for item in extracted]
                else:
                    data[field] = grounded_value(field, extracted, request.message) if extracted else None
            except ValueError:
                uncertain.append(field)
        required = ("job_title", "role_summary", "responsibilities", "required_skills")
        uncertain += [field for field in required if not data.get(field) and field not in uncertain]
        if not uncertain:
            try:
                jd_request = JobDescriptionGenerationRequest.model_validate(data)
            except ValidationError as error:
                uncertain = list(dict.fromkeys(
                    str(e["loc"][0]) for e in error.errors() if e["loc"]
                )) or ["required_skills", "preferred_skills"]
        if uncertain:
            return ClarificationResponse(missing_fields=uncertain,
                assistant_message="Please clarify " + ", ".join(FIELD_LABELS[f] for f in uncertain)
                + ". Edit and resend your complete instruction with positively stated requirements; each request is independent.")
        result = await self._workflow_factory().generate(jd_request)
        return JobDescriptionChatResponse(job_description_result=result,
            screening_suggestions=screening_suggestions(jd_request), publishing_context=PublishingContext(
            location=jd_request.location, employment_type=jd_request.employment_type, work_arrangement=jd_request.work_arrangement))
