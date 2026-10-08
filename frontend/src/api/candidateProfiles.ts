import type { CandidateProfilesResponse } from "../types/candidateProfile";
import type { CvUploadResponse } from "../types/cvUpload";
import { isCvUploadResponse } from "./cvUploads.ts";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function record(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function keys(value: unknown, names: readonly string[]): value is Record<string, unknown> {
  return record(value) && Object.keys(value).length === names.length && names.every(name => Object.hasOwn(value, name));
}
function attribute(value: unknown): boolean {
  if (!keys(value, ["value", "source"]) || typeof value.value !== "string" || !value.value.trim() || value.value.length > 500
    || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value.value)) return false;
  const source = value.source;
  return keys(source, ["kind", "number", "method", "block_type"]) && Number.isInteger(source.number) && Number(source.number) >= 1
    && (source.kind === "page" ? Number(source.number) <= 200 && (source.method === "digital" || source.method === "ocr") && source.block_type === null
      : source.kind === "block" && Number(source.number) <= 10000 && source.method === "digital" && (source.block_type === "paragraph" || source.block_type === "table_cell"));
}
const optional = (value: unknown) => value === null || attribute(value);
export { attribute as isGroundedAttribute };
const attributes = (value: unknown, maximum: number) => Array.isArray(value) && value.length <= maximum && value.every(attribute);
function contact(value: unknown): boolean {
  return keys(value, ["candidate_name", "emails", "phones", "links", "location"]) && optional(value.candidate_name)
    && attributes(value.emails, 5) && attributes(value.phones, 5) && attributes(value.links, 10) && optional(value.location);
}
function qualifications(value: unknown): boolean {
  return keys(value, ["education", "work_history", "skills"])
    && Array.isArray(value.education) && value.education.length <= 20 && value.education.every(entry =>
      keys(entry, ["institution", "qualification", "field_of_study", "date_or_period"]) && Object.values(entry).every(optional))
    && Array.isArray(value.work_history) && value.work_history.length <= 20 && value.work_history.every(entry =>
      keys(entry, ["employer", "role_title", "date_or_period", "location", "responsibilities_or_achievements"])
      && [entry.employer, entry.role_title, entry.date_or_period, entry.location].every(optional) && attributes(entry.responsibilities_or_achievements, 20))
    && attributes(value.skills, 100);
}

export function isCandidateProfilesResponse(value: unknown): value is CandidateProfilesResponse {
  return keys(value, ["status", "job_reference", "batch_id", "processed_count", "candidates"])
    && value.status === "processed" && typeof value.job_reference === "string" && /^TT-JOB-[A-F0-9]{16}$/.test(value.job_reference)
    && typeof value.batch_id === "string" && UUID.test(value.batch_id)
    && Number.isInteger(value.processed_count) && Number(value.processed_count) >= 1 && Number(value.processed_count) <= 20
    && Array.isArray(value.candidates) && value.candidates.length === value.processed_count
    && new Set(value.candidates.map(item => record(item) ? item.upload_id : null)).size === value.candidates.length
    && value.candidates.every(item => keys(item, ["upload_id", "parsing_status", "contact", "qualifications"])
      && typeof item.upload_id === "string" && UUID.test(item.upload_id)
      && (item.parsing_status === "parsed" ? contact(item.contact) && qualifications(item.qualifications)
        : (item.parsing_status === "source_unavailable" || item.parsing_status === "parsing_failed") && item.contact === null && item.qualifications === null));
}

export async function extractCandidateProfiles(batch: CvUploadResponse): Promise<CandidateProfilesResponse> {
  if (!isCvUploadResponse(batch)) throw new Error("A valid uploaded batch is required.");
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/cv-uploads/${batch.job_reference}/${batch.batch_id}/candidate-profiles`, {method: "POST"});
  } catch { throw new Error("Candidate extraction was not confirmed. Check before retrying; another request can repeat provider calls."); }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(response.status === 503 && record(body) && body.code === "candidate_parser_not_configured"
    ? "Candidate profile extraction is not configured on this server." : "Candidate profile extraction could not be completed.");
  if (!isCandidateProfilesResponse(body) || body.job_reference !== batch.job_reference || body.batch_id !== batch.batch_id
    || body.processed_count !== batch.accepted_count || body.candidates.some(item => !batch.files.some(file => file.upload_id === item.upload_id))) {
    throw new Error("Candidate extraction returned an invalid confirmation.");
  }
  return body;
}
