"""Contact-free requirement counts within one confirmed screening snapshot."""
from collections import Counter
from collections.abc import Sequence

from app.schemas.screening import ScreeningCriterion, ScreeningDecisionResult


def rank_eligible_candidates(results: Sequence[ScreeningDecisionResult], *,
                             job_reference: str, criteria: Sequence[ScreeningCriterion]) -> list[dict]:
    """Competition ranks (1, 1, 3); UUID ordering only stabilizes tied display."""
    if not 1 <= len(criteria) <= 50 or len(results) > 20:
        raise ValueError("Ranking requires bounded confirmed requirements and results.")
    criterion_ids = [c.criterion_id for c in criteria]
    if len(set(c.casefold() for c in criterion_ids)) != len(criterion_ids):
        raise ValueError("Ranking requires unique requirements.")
    rows, seen = [], set()
    for supplied in results:
        result = ScreeningDecisionResult.model_validate(supplied.model_dump(warnings=False))
        context = result.matching_result.requirement_context
        if (result.job_reference != job_reference or result.upload_id in seen
                or any(getattr(context, f"{category}_ids") != tuple(
                    c.criterion_id for c in criteria if c.category == category)
                    for category in ("skill", "experience", "education"))
                or context.hard_requirement_ids != tuple(c.criterion_id for c in criteria if c.is_hard)):
            raise ValueError("Ranking results must share one confirmed job snapshot.")
        seen.add(result.upload_id)
        if result.status != "decision_complete":
            continue
        matches = result.matching_result.matches
        if set(m.criterion_id for m in matches) != set(criterion_ids):
            raise ValueError("Ranking requires complete requirement coverage.")
        if result.screening_decision != "eligible":
            continue
        counts = Counter(m.match_status for m in matches)
        rows.append(dict(upload_id=result.upload_id, supported_count=counts["supported"],
                         ambiguous_count=counts["ambiguous"], not_found_count=counts["not_found"],
                         total_requirements=len(criteria)))
    rows.sort(key=lambda row: (-row["supported_count"], row["upload_id"].hex))
    frequencies = Counter(row["supported_count"] for row in rows)
    previous, rank = None, 0
    for position, row in enumerate(rows, start=1):
        if row["supported_count"] != previous:
            rank = position
        previous = row["supported_count"]
        row.update(rank=rank, tied=frequencies[previous] > 1)
    return rows
