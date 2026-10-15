import { authenticatedFetch } from "./session.ts";
import type { JobDescriptionGenerationResponse } from "../types/jobDescription";
import type { PublicationResult, PublishingContext } from "../types/recruiterChat";
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export async function prepareLinkedInDraft(result: JobDescriptionGenerationResponse, context: PublishingContext = {}, jobId?: string): Promise<{destination: "linkedin"; status: "prepared"; mode: "manual"; announcement: string}> {
  if (!jobId) throw new Error("Select a saved job first.");
  const draft = result.job_description;
  const response = await authenticatedFetch(`${API_BASE_URL}/api/v1/recruiter-chat/linkedin/prepare`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({job_id: jobId, title: draft.title, summary: draft.summary,
      responsibilities: draft.responsibilities, required_skills: draft.required_skills,
      preferred_skills: draft.preferred_skills, qualifications: draft.qualifications,
      ...(context.location ? {location: context.location} : {}),
      ...(context.employment_type ? {employment_type: context.employment_type} : {}),
      ...(context.work_arrangement ? {work_arrangement: context.work_arrangement} : {})}),
  });
  if (!response.ok) throw new Error("LinkedIn preparation failed. Nothing was published.");
  const body = await response.json();
  if (body?.destination !== "linkedin" || body?.status !== "prepared" || body?.mode !== "manual"
    || typeof body.announcement !== "string" || !body.announcement.trim() || body.announcement.length > 3000)
    throw new Error("Invalid LinkedIn preparation response. Nothing was published.");
  return body;
}

export async function publishDraft(result: JobDescriptionGenerationResponse, context: PublishingContext = {}, jobId?: string): Promise<PublicationResult> {
  const draft = result.job_description;
  let response: Response;
  try {
    response = await authenticatedFetch(`${API_BASE_URL}/api/v1/recruiter-chat/publish`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({...(jobId ? {job_id: jobId} : {}), title: draft.title, summary: draft.summary,
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
