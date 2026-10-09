"""Deterministic weighted requirement coverage; separate from eligibility/ranking."""
from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.candidate_score import CandidateScore, DimensionScore, ScoringWeights
from app.schemas.screening import ScreeningCriterion, ScreeningDecisionResult
from app.services.screening_ranking import validate_screening_snapshot


def rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def score_candidate(result: ScreeningDecisionResult, *, job_reference: str,
                    criteria: Sequence[ScreeningCriterion], weights: ScoringWeights | None = None) -> CandidateScore:
    """Inputs must come from server-validated screening, never client verdicts."""
    weights = ScoringWeights.model_validate((weights or ScoringWeights()).model_dump())
    result = validate_screening_snapshot(result, job_reference=job_reference, criteria=criteria)
    reason = None
    if result.status != "decision_complete":
        reason = "screening_incomplete"
    elif result.screening_decision != "eligible":
        reason = "not_eligible"
    groups = {category: tuple(m for m in result.matching_result.matches if m.criterion_id in {
        c.criterion_id for c in criteria if c.category == category})
        for category in ("skill", "experience", "education")}
    if reason is None:
        if any(getattr(weights, category) > 0 and any(m.match_status == "ambiguous" for m in matches)
               for category, matches in groups.items()):
            reason = "uncertain_evidence"
        elif any(getattr(weights, category) > 0 and not matches for category, matches in groups.items()):
            reason = "missing_dimension_criteria"
    identity = dict(job_reference=result.job_reference, upload_id=result.upload_id,
                    screening_decision=result.screening_decision, weights=weights)
    if reason:
        return CandidateScore(**identity, status="not_evaluated", reason=reason, score=None, dimensions=())
    dimensions, total = [], Decimal(0)
    for category, matches in groups.items():
        supported = sum(m.match_status == "supported" for m in matches)
        ratio = Decimal(supported) / len(matches) if matches else None
        weight = getattr(weights, category)
        points = Decimal(weight) * ratio if ratio is not None else Decimal(0)
        total += points
        dimensions.append(DimensionScore(category=category, weight=weight, supported_count=supported,
            total_requirements=len(matches), coverage_percent=rounded(100 * ratio) if ratio is not None else None,
            weighted_points=rounded(points), matches=matches))
    return CandidateScore(**identity, status="scored", reason=None, score=rounded(total), dimensions=tuple(dimensions))
