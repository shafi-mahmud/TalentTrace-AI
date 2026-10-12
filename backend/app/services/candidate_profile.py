"""Request-scoped source resolution and conservative textual grounding; no scoring."""
import re
import unicodedata
import logging
import time
from uuid import UUID
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, settings
from app.integrations.llm.candidate_profile import (
    CandidateParserNotConfigured, CandidateProfileExtractor, GroqCandidateProfileExtractor,
)

logger = logging.getLogger("talenttrace.screening_diagnostics")


class CandidateEvidenceError(ValueError):
    """Internal diagnostic reason; never stores the submitted value or quote."""
    def __init__(self, code):
        self.code=code
        super().__init__("Candidate evidence failed validation.")
from app.schemas.candidate_profile import (
    CandidateContact, CandidateEducation, CandidateProfile, CandidateProfileInterpretation,
    CandidateQualifications, CandidateSourceDocument, CandidateSourceUnit, CandidateWorkHistory,
    EvidenceValue, GroundedAttribute, SourceReference,
)
from app.services.cv_extraction import CvExtractionService
from app.services.cv_ocr import CvOcrService, OcrNotConfigured


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def grounded(item: EvidenceValue | None, units: dict[str, CandidateSourceUnit], field: str = "") -> GroundedAttribute | None:
    if item is None:
        return None
    unit = units.get(item.source_id)
    if unit is None:
        raise CandidateEvidenceError("unknown_source")
    evidence, source = normalized(item.evidence), normalized(unit.text)
    value = normalized(item.value).rstrip(" .;:")
    if not evidence or not re.search(r"(?<!\w)" + re.escape(evidence) + r"(?!\w)", source):
        raise CandidateEvidenceError("quote_not_in_source")
    if not value or not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", evidence):
        raise CandidateEvidenceError("value_not_in_quote")
    if field == "candidate_name":
        plain = " ".join(token for token in source.split() if "@" not in token and "://" not in token)
        if not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", plain):
            raise ValueError("A name cannot be inferred from contact addresses.")
    display = " ".join(unicodedata.normalize("NFC", item.value).split()).rstrip(" .;:")
    limits = {"candidate_name": 200, "emails": 254, "phones": 64, "links": 500, "location": 200, "skills": 80}
    if len(display) > limits.get(field, 500):
        raise ValueError("Candidate fact exceeds field limit.")
    if field == "emails" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", display):
        raise ValueError("Invalid contact email.")
    if field == "phones" and not re.fullmatch(r"\+?[0-9][0-9 ()+.-]{3,62}[0-9]", display):
        raise ValueError("Invalid contact phone.")
    if field == "links":
        parsed = urlsplit(display)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid contact link.")
    return GroundedAttribute(value=display, source=unit.source)


def validate_profile(upload_id: UUID, interpretation: CandidateProfileInterpretation, document: CandidateSourceDocument) -> CandidateProfile:
    interpretation = CandidateProfileInterpretation.model_validate(interpretation.model_dump())
    units = {unit.source_id: unit for unit in document.units}
    def one(value, field=""): return grounded(value, units, field)
    contact = interpretation.contact
    qualifications = interpretation.qualifications
    education = [CandidateEducation(**{field: one(getattr(entry, field)) for field in CandidateEducation.model_fields}) for entry in qualifications.education]
    history = []
    for entry in qualifications.work_history:
        history.append(CandidateWorkHistory(employer=one(entry.employer), role_title=one(entry.role_title),
            date_or_period=one(entry.date_or_period), location=one(entry.location, "location"),
            responsibilities_or_achievements=[one(value) for value in entry.responsibilities_or_achievements]))
    # Validate every skill first, even duplicates; retain earliest document source.
    skills = [one(value, "skills") for value in qualifications.skills]
    order = {unit.source_id: index for index, unit in enumerate(document.units)}
    def skill_position(value):
        source_id = f"{value.source.kind}:{value.source.number}"
        position = re.search(r"(?<!\w)" + re.escape(normalized(value.value)) + r"(?!\w)", normalized(units[source_id].text))
        return (order[source_id], position.start())
    skills.sort(key=skill_position)
    seen, unique = set(), []
    for skill in skills:
        key = normalized(skill.value)
        if key not in seen:
            seen.add(key); unique.append(skill)
    return CandidateProfile(upload_id=upload_id, parsing_status="parsed",
        contact=CandidateContact(candidate_name=one(contact.candidate_name, "candidate_name"),
            emails=[one(value, "emails") for value in contact.emails], phones=[one(value, "phones") for value in contact.phones],
            links=[one(value, "links") for value in contact.links], location=one(contact.location, "location")),
        qualifications=CandidateQualifications(education=education, work_history=history, skills=unique))


class CandidateProfileService:
    def __init__(self, configuration: Settings | None = None, *, extractor: CandidateProfileExtractor | None = None):
        self.configuration = configuration or settings
        self.extractor = extractor or GroqCandidateProfileExtractor(self.configuration)
        self.extraction = CvExtractionService(self.configuration.cv_upload_root)
        self.ocr = CvOcrService(self.configuration.cv_upload_root, self.configuration.ocr_tessdata_path)

    def _sources(self, job_reference: str, batch_id: UUID):
        extracted = self.extraction.extract_batch_with_paths(job_reference, batch_id)
        try:
            ocr_results = {result.upload_id: result for result in self.ocr.process_extracted(extracted)}
        except OcrNotConfigured:
            ocr_results = {}
        sources = []
        for _, primary in extracted:
            units = primary.source_units if primary.extraction_status == "text_extracted" else None
            if primary.extraction_status == "ocr_required":
                result = ocr_results.get(primary.upload_id)
                units = result.source_units if result and result.ocr_status == "ocr_extracted" else None
            if units is None:
                sources.append((primary.upload_id, "source_unavailable", None)); continue
            try:
                converted = []
                for unit in units:
                    if primary.file_type == "pdf":
                        locator = SourceReference(kind="page", number=unit.page_number,
                            method=getattr(unit, "source_method", "digital"))
                    else:
                        locator = SourceReference(kind="block", number=unit.block_index, method="digital", block_type=unit.block_type)
                    converted.append(CandidateSourceUnit(source_id=f"{locator.kind}:{locator.number}", source=locator, text=unit.text))
                document = CandidateSourceDocument(upload_id=primary.upload_id, units=tuple(converted))
                sources.append((primary.upload_id, None, document))
            except ValueError:
                logger.warning("talenttrace_failure stage=candidate_source category=source_contract_invalid")
                sources.append((primary.upload_id, "parsing_failed", None))
        return sources

    async def parse_batch(self, job_reference: str, batch_id: UUID) -> tuple[CandidateProfile, ...]:
        # Validate storage before any provider call; missing configuration is request-level.
        await run_in_threadpool(self.extraction.batch_files, job_reference, batch_id)
        if self.configuration.groq_api_key is None or not self.configuration.groq_api_key.get_secret_value().strip():
            raise CandidateParserNotConfigured()
        sources = await run_in_threadpool(self._sources, job_reference, batch_id)
        candidates = []
        for index, (upload_id, failure, document) in enumerate(sources,1):
            started = time.perf_counter()
            if failure:
                candidates.append(CandidateProfile(upload_id=upload_id, parsing_status=failure, contact=None, qualifications=None)); continue
            try:
                interpretation = await self.extractor.extract(document)
                candidates.append(validate_profile(upload_id, interpretation, document))
            except CandidateParserNotConfigured:
                raise
            except Exception as error:
                from app.integrations.llm.candidate_profile import CandidateProviderError
                category = "profile_provider_failed" if isinstance(error,CandidateProviderError) else error.code if isinstance(error,CandidateEvidenceError) else "profile_evidence_or_contract_invalid"
                logger.warning("talenttrace_failure stage=candidate_profile_validation candidate_index=%s category=%s exception_class=%s",index,category,type(error).__name__)
                candidates.append(CandidateProfile(upload_id=upload_id, parsing_status="parsing_failed", contact=None, qualifications=None))
            logger.info("talenttrace_stage stage=candidate_profile candidate_index=%s status=%s duration_ms=%s",index,candidates[-1].parsing_status,int((time.perf_counter()-started)*1000))
        return tuple(candidates)
