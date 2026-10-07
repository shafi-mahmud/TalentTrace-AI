import type { JobDescriptionGenerationResponse } from "../types/jobDescription";
import type { PublicationResult, PublishingContext } from "../types/recruiterChat";
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export async function publishDraft(result: JobDescriptionGenerationResponse, context: PublishingContext = {}): Promise<PublicationResult> {
  const draft = result.job_description;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/recruiter-chat/publish`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({title: draft.title, summary: draft.summary,
        responsibilities: draft.responsibilities, required_skills: draft.required_skills,
        preferred_skills: draft.preferred_skills, qualifications: draft.qualifications,
        ...(context.location ? {location: context.location} : {}),
        ...(context.employment_type ? {employment_type: context.employment_type} : {}),
        ...(context.work_arrangement ? {work_arrangement: context.work_arrangement} : {}),
      }),
    });
  } catch { throw new Error("Publication was not confirmed. Check Discord before another attempt."); }
  if (!response.ok) throw new Error(response.status === 422
    ? "Draft cannot be published within the content limits. Revise it first."
    : response.status === 503 ? "Job publishing is not configured."
    : "Publication was not confirmed. Check Discord before another attempt.");
  const body: unknown = await response.json().catch(() => null);
  if (typeof body !== "object" || body === null || !("destination" in body) || !("status" in body) || !("external_id" in body)
      || body.destination !== "discord" || body.status !== "published" || typeof body.external_id !== "string" || !/^[0-9]{17,20}$/.test(body.external_id)) {
    throw new Error("Publication was not confirmed. Check Discord before another attempt.");
  }
  return {destination: body.destination, status: body.status, external_id: body.external_id};
}
