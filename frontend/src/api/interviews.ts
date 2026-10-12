import { authenticatedFetch } from "./session.ts";

export interface InterviewRequest {
  batch_id: string; upload_id: string; criteria_revision: number; scoring_version: "f2-coverage-v1";
  selection_confirmed: true; confirm_eligible_unscored: boolean; scheduled_at: string; timezone: string; duration_minutes: number;
}
export interface Interview {
  id: string; job_id: string; job_reference: string; batch_id: string; upload_id: string;
  criteria_revision: number; scoring_version: "f2-coverage-v1"; scheduled_at: string;
  timezone: string; duration_minutes: number; unscored_confirmed: boolean; status: "scheduled";
}
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const base = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export function validTimezone(zone: unknown): zone is string {
  if (typeof zone !== "string" || zone.length > 64 || !/^[A-Za-z0-9_+/-]+$/.test(zone)) return false;
  try {new Intl.DateTimeFormat("en", {timeZone: zone}); return true;} catch {return false;}
}
export function isInterview(value: unknown): value is Interview {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const v = value as Interview;
  const names = ["id", "job_id", "job_reference", "batch_id", "upload_id", "criteria_revision", "scoring_version", "scheduled_at", "timezone", "duration_minutes", "unscored_confirmed", "status"];
  return Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v, n))
    && [v.id,v.job_id,v.batch_id,v.upload_id].every(id => typeof id === "string" && uuid.test(id))
    && /^TT-JOB-[A-F0-9]{16}$/.test(v.job_reference) && v.status === "scheduled" && v.scoring_version === "f2-coverage-v1"
    && Number.isInteger(v.criteria_revision) && v.criteria_revision > 0 && validTimezone(v.timezone)
    && typeof v.scheduled_at === "string" && /(?:Z|\+00:00)$/.test(v.scheduled_at) && Number.isFinite(Date.parse(v.scheduled_at))
    && Number.isInteger(v.duration_minutes) && v.duration_minutes >= 15 && v.duration_minutes <= 180 && typeof v.unscored_confirmed === "boolean";
}
export async function createInterview(jobId: string, request: InterviewRequest): Promise<Interview> {
  let response: Response;
  try {response = await authenticatedFetch(`${base}/api/v1/jobs/${jobId}/interviews`, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(request)});
  } catch {throw new Error("Scheduling was not confirmed. Reload saved interviews before another attempt.");}
  if (!response.ok) throw new Error(response.status === 409 ? "Scheduling needs review: check current eligibility, revision, confirmation and existing interviews."
    : response.status === 422 ? "Check the future interview time, timezone and duration." : "Interview could not be scheduled.");
  const value: unknown = await response.json().catch(() => null);
  if (!isInterview(value) || value.job_id !== jobId || value.batch_id !== request.batch_id || value.upload_id !== request.upload_id
    || value.criteria_revision !== request.criteria_revision || value.timezone !== request.timezone || value.duration_minutes !== request.duration_minutes
    || Date.parse(value.scheduled_at) !== Date.parse(request.scheduled_at)
    || (value.unscored_confirmed && !request.confirm_eligible_unscored)) throw new Error("Saved interview could not be validated. Reload interviews before another attempt.");
  return value;
}
export async function listInterviews(jobId: string): Promise<Interview[]> {
  const response = await authenticatedFetch(`${base}/api/v1/jobs/${jobId}/interviews`);
  if (!response.ok) throw new Error("Saved interviews could not be loaded.");
  const value: unknown = await response.json().catch(() => null);
  if (!Array.isArray(value) || value.length > 100 || !value.every(v => isInterview(v) && v.job_id === jobId)
    || new Set(value.map(v => v.id)).size !== value.length) throw new Error("Saved interviews could not be validated.");
  return value;
}
