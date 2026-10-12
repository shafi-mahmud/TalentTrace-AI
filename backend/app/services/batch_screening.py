"""One request-scoped parser/screening execution with deterministic ranking."""
from uuid import UUID
import logging
import time

from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.schemas.batch_screening import BatchScreeningItem, BatchScreeningResponse, ReviewedJobSnapshot, ScreeningSuggestions, overall_requirement_coverage
from app.schemas.job_description import JobDescriptionGenerationRequest
from app.schemas.screening import ScreeningCriterion, ScreeningInput
from app.services.candidate_profile import CandidateProfileService
from app.services.screening_ranking import rank_eligible_candidates

logger = logging.getLogger("talenttrace.screening_diagnostics")


class JobSnapshotMismatch(ValueError):
    pass


def screening_suggestions(request: JobDescriptionGenerationRequest) -> ScreeningSuggestions:
    """Source-backed recruiter requirements only; no generated JD additions."""
    values = [("skill", text) for text in request.required_skills + request.preferred_skills]
    values += [("education", text) for text in request.education_requirements]
    if request.minimum_experience_years is not None and request.minimum_experience_years > 0:
        values.append(("experience", f"Minimum {request.minimum_experience_years} years of relevant experience"))
    return ScreeningSuggestions(job_title=request.job_title, criteria=[
        ScreeningCriterion(criterion_id=f"criterion-{index:02d}", category=category,
            description=text, is_hard=False)
        for index, (category, text) in enumerate(values, start=1)])


class BatchScreeningService:
    def __init__(self, profiles: CandidateProfileService | None = None,
                 workflow: CandidateScreeningWorkflow | None = None):
        self.profiles = profiles if profiles is not None else CandidateProfileService()
        self.workflow = workflow if workflow is not None else CandidateScreeningWorkflow()

    async def screen_batch(self, job_reference: str, batch_id: UUID,
                           snapshot: ReviewedJobSnapshot) -> BatchScreeningResponse:
        snapshot = ReviewedJobSnapshot.model_validate(snapshot.model_dump(warnings=False))
        if snapshot.job_reference != job_reference:
            raise JobSnapshotMismatch("The reviewed snapshot must match the uploaded job reference.")
        # Resolve the private stored batch once; browser-supplied qualifications are never accepted.
        started_batch=time.perf_counter()
        profiles = await self.profiles.parse_batch(job_reference, batch_id)
        candidates = []
        for index, profile in enumerate(profiles,1):
            started=time.perf_counter()
            try:
                supplied = ScreeningInput(job_reference=job_reference, upload_id=profile.upload_id,
                    parsing_status=profile.parsing_status, qualifications=profile.qualifications,
                    criteria=tuple(snapshot.criteria))
                result = await self.workflow.screen(supplied)
                logger.info("talenttrace_stage stage=screening candidate_index=%s status=%s category=%s duration_ms=%s",index,result.status,result.matching_result.error_code,int((time.perf_counter()-started)*1000))
                candidates.append(BatchScreeningItem(upload_id=profile.upload_id, result=result, error_code=None,
                    overall_coverage=overall_requirement_coverage(result)))
            except Exception as error:
                logger.warning("talenttrace_failure stage=screening candidate_index=%s category=screening_processing_failed exception_class=%s",index,type(error).__name__)
                # Unexpected candidate-level failures are operational, never exclusions.
                candidates.append(BatchScreeningItem(upload_id=profile.upload_id,
                    result=None, error_code="screening_processing_failed", overall_coverage="not_evaluated"))
        logger.info("talenttrace_stage stage=batch_matching candidate_count=%s duration_ms=%s",len(candidates),int((time.perf_counter()-started_batch)*1000))
        return BatchScreeningResponse(job_reference=job_reference, batch_id=batch_id,
            snapshot=snapshot, processed_count=len(candidates), candidates=candidates,
            ranking=rank_eligible_candidates([c.result for c in candidates if c.result is not None],
                job_reference=job_reference, criteria=snapshot.criteria))
