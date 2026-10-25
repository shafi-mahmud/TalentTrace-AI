import { authenticatedFetch } from "./session.ts";
import type { JobDescriptionGenerationResponse } from "../types/jobDescription";
import type { PublicationResult, PublishingContext, AutomaticDestination } from "../types/recruiterChat";
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export async function publishDraft(result: JobDescriptionGenerationResponse, context: PublishingContext = {}, jobId?: string, destination:AutomaticDestination="discord"): Promise<PublicationResult> {
  if(!["discord","telegram"].includes(destination))throw Error("Unsupported automatic destination.");
  const draft = result.job_description;
  let response: Response;
  try {
    response = await authenticatedFetch(`${API_BASE_URL}/api/v1/recruiter-chat/publish`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({...(destination==="telegram"?{destination}:{}),...(jobId ? {job_id: jobId} : {}), title: draft.title, summary: draft.summary,
        responsibilities: draft.responsibilities, required_skills: draft.required_skills,
        preferred_skills: draft.preferred_skills, qualifications: draft.qualifications,
        ...(context.location ? {location: context.location} : {}),
        ...(context.employment_type ? {employment_type: context.employment_type} : {}),
        ...(context.work_arrangement ? {work_arrangement: context.work_arrangement} : {}),
      }),
    });
  } catch { throw new Error("Publication was not confirmed. Check the selected destination before another attempt."); }
  if (!response.ok) throw new Error(response.status === 422
    ? "Draft cannot be published within the content limits. Revise it first."
    : response.status === 503 ? "Job publishing is not configured."
    : "Publication was not confirmed. Check the selected destination before another attempt.");
  const body: unknown = await response.json().catch(() => null);
  if (typeof body !== "object" || body === null || !("destination" in body) || !("status" in body) || !("external_id" in body)
      || body.destination !== destination || body.status !== "published" || typeof body.external_id !== "string" || !(destination==="discord"?/^[0-9]{17,20}$/:/^[1-9][0-9]{0,19}$/).test(body.external_id)) {
    throw new Error("Publication was not confirmed. Check the selected destination before another attempt.");
  }
  return {destination,  status: body.status, external_id: body.external_id};
}
