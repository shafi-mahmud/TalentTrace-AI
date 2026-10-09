"""Conservative curated demo rules; prose is reference data, never executable rules."""
import re

from app.schemas.job_description import JobDescriptionGenerationRequest, PolicyScreeningSuggestion

# Pin the approved demo revision, not just a caller-supplied identity/version.
APPROVED_DEMO_SHA256 = "5796b423bf1c4e70a288be18ed4c03fd10d35384cd304fb49a2770decf71ea8f"


def policy_screening_suggestions(request: JobDescriptionGenerationRequest, chunks):
    # This is an explicit, reviewed mapping of concrete demo-policy practices.
    # Fairness, work location, availability and protected traits are NOT CV criteria.
    role = " ".join([request.role_summary, *request.responsibilities, *request.required_skills]).casefold()
    if not re.search(r"\b(?:secure|security|privacy)\b|data protection", role):
        return []
    rules = [("access-controls", "Applying access controls", "following access controls"),
             ("incident-reporting", "Reporting security incidents", "reporting incidents")]
    output = []
    for code, description, evidence in rules:
        for item in chunks:
            # Only the declared synthetic policy/version is approved for these demo mappings.
            if (item.source.source_id.hex != "6c3edcb71a634feeb535b6155efdbf42" or
                item.source.source_version != "synthetic-demo-v1" or
                item.source.content_sha256 != APPROVED_DEMO_SHA256 or
                not any("Data Protection and Privacy Expectations" in path for path in item.chunk.metadata.heading_paths)):
                continue
            match = re.search(re.escape(evidence), item.chunk.text, re.I)
            if match:
                output.append(PolicyScreeningSuggestion(criterion_id=f"policy-{code}", description=description,
                    evidence=match.group(), citation_id=item.chunk.metadata.citation_id, source_title=item.source.title))
                break
    return output
