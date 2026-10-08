"""Conservative exact matching and validation of semantic evidence references."""
import unicodedata

from app.schemas.screening import (
    MatchEvidence, MatchingErrorCode, QualificationFact, RequirementMatch,
    ScreeningCriterion, ScreeningInput, SemanticMatchingResponse,
)


class ScreeningMatchingError(Exception):
    def __init__(self, code: MatchingErrorCode):
        self.code = code
        super().__init__("Candidate requirement matching could not be completed.")


def normalized(value: str) -> str:
    # Preserve meaningful punctuation (C++, C#, Node.js); no substring/fuzzy matching.
    return " ".join(unicodedata.normalize("NFC", value).casefold().split()).removesuffix(".")


def qualification_facts(request: ScreeningInput) -> tuple[QualificationFact, ...]:
    qualifications = request.qualifications
    if qualifications is None:
        return ()
    facts = []
    def add(kind, attribute, record_group=None):
        if attribute is not None:
            facts.append(QualificationFact(fact_id=f"fact:{len(facts) + 1:04d}",
                record_group=record_group, kind=kind, value=attribute.value, source=attribute.source))
    for skill in qualifications.skills:
        add("skill", skill)
    for index, education in enumerate(qualifications.education, start=1):
        group = f"education:{index:02d}"
        add("education_qualification", education.qualification, group)
        add("education_field", education.field_of_study, group)
    for index, work in enumerate(qualifications.work_history, start=1):
        group = f"work:{index:02d}"
        add("work_role", work.role_title, group)
        add("work_period", work.date_or_period, group)
        for activity in work.responsibilities_or_achievements:
            add("work_activity", activity, group)
    return tuple(facts)


def relevant_facts(criterion: ScreeningCriterion, facts: tuple[QualificationFact, ...]):
    kinds = {
        "skill": {"skill", "work_role", "work_activity"},
        "education": {"education_qualification", "education_field"},
        "experience": {"work_role", "work_period", "work_activity"},
    }[criterion.category]
    return tuple(fact for fact in facts if fact.kind in kinds)


def make_match(criterion_id, status, method, facts):
    explanations = {
        ("supported", "deterministic"): "A supplied qualification value directly matches this criterion.",
        ("not_found", "deterministic"): "No qualification facts in the relevant categories were supplied; this is not a rejection.",
        ("supported", "semantic"): "Semantic interpretation supports this criterion using referenced facts; human review is required.",
        ("ambiguous", "semantic"): "Referenced facts are related but insufficient for confident support; human review is required.",
        ("not_found", "semantic"): "Supporting evidence was not identified in the supplied facts; this is not a rejection.",
    }
    return RequirementMatch(criterion_id=criterion_id, match_status=status, match_method=method,
        evidence=tuple(MatchEvidence(fact_id=f.fact_id, value=f.value, source=f.source) for f in facts),
        explanation=explanations[(status, method)])


def deterministic_matches(criteria, facts):
    resolved, unresolved = [], []
    for criterion in criteria:
        relevant = relevant_facts(criterion, facts)
        # Period strings alone cannot establish a skill/role or an experience total.
        exact = tuple(f for f in relevant if f.kind != "work_period"
            and normalized(f.value) == normalized(criterion.description))
        if exact:
            resolved.append(make_match(criterion.criterion_id, "supported", "deterministic", exact[:8]))
        elif not relevant:
            resolved.append(make_match(criterion.criterion_id, "not_found", "deterministic", ()))
        else:
            unresolved.append(criterion)
    return tuple(resolved), tuple(unresolved)


def validate_semantic_matches(response: SemanticMatchingResponse, criteria, facts):
    try:
        response = SemanticMatchingResponse.model_validate(response.model_dump(warnings=False))
        expected = {c.criterion_id: c for c in criteria}
        results = {r.criterion_id: r for r in response.results}
        if len(results) != len(response.results) or set(results) != set(expected):
            raise ValueError
        validated = []
        for criterion in criteria:
            result = results[criterion.criterion_id]
            allowed = {f.fact_id: f for f in relevant_facts(criterion, facts)}
            evidence = []
            for ref in result.evidence:
                fact = allowed.get(ref.fact_id)
                if fact is None or normalized(fact.value) != normalized(ref.value):
                    raise ValueError
                evidence.append(fact)
            status = result.match_status
            cross_record_support = (criterion.category == "education" and status == "supported"
                and len({fact.record_group for fact in evidence}) > 1)
            if cross_record_support:
                # No keyword heuristics: separate records cannot establish one linked degree/field.
                # Broad legitimate multi-record requirements remain conservatively ambiguous too.
                status = "ambiguous"
            match = make_match(criterion.criterion_id, status, "semantic", evidence)
            if cross_record_support:
                match = match.model_copy(update={"explanation":
                    "Education evidence spans separate records; a single-record association is not established."})
            validated.append(match)
        return tuple(validated)
    except Exception:
        raise ScreeningMatchingError("invalid_semantic_response") from None
