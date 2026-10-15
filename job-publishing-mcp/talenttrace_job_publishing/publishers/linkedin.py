"""Offline LinkedIn announcement adapter. Never authenticates or publishes."""
from ..schemas import JobCircular, LinkedInPreparation


class LinkedInPublisher:
    def prepare(self, job: JobCircular) -> LinkedInPreparation:
        # Bound each section instead of silently dropping requirements at the end.
        lines = [job.title, f"Job reference: {job.job_reference}"]
        if job.location:
            lines.append(f"Location: {job.location}")
        if job.employment_type:
            lines.append(f"Employment: {job.employment_type.replace('_', ' ')}")
        if job.work_arrangement:
            lines.append(f"Work arrangement: {job.work_arrangement}")
        lines.extend(["", job.summary[:500]])
        for title, items in [("Responsibilities", job.responsibilities),
                             ("Required skills", job.required_skills),
                             ("Preferred skills", job.preferred_skills),
                             ("Qualifications", job.qualifications)]:
            if items:
                text = "; ".join(items)
                lines.append(f"{title}: {text[:350]}" + ("… (see full job description)" if len(text) > 350 else ""))
        if len(job.summary) > 500:
            lines.append("Summary shortened; review the full job description before sharing.")
        if job.application_url:
            lines.extend(["", f"Apply: {job.application_url}", "Include the job reference in your application."])
        return LinkedInPreparation(announcement="\n".join(lines))
