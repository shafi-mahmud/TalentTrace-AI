import {authenticatedFetch} from "./session.ts";
const BASE = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export interface ApplicationItem {batch_id: string; upload_id: string; origin: "native_storage" | "trusted_import"; available: boolean; is_new: boolean;}
export interface Applications {job_id: string; received_count: number; new_count: number; unavailable_count: number; invalid_batch_count: number; applications: ApplicationItem[];}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function validateApplications(value: unknown, jobId: string): Applications {
  const v = value as Applications;
  if (!v || Object.keys(v).sort().join() !== ["job_id","received_count","new_count","unavailable_count","invalid_batch_count","applications"].sort().join() || v.job_id !== jobId || !Array.isArray(v.applications) || v.applications.length > 1000
    || ![v.received_count,v.new_count,v.unavailable_count,v.invalid_batch_count].every(n=>Number.isInteger(n)&&n>=0)) throw new Error("Invalid application summary.");
  const keys = new Set<string>();
  for (const row of v.applications) {
    if (!row || Object.keys(row).sort().join() !== ["batch_id","upload_id","origin","available","is_new"].sort().join() || !uuid.test(row.batch_id) || !uuid.test(row.upload_id) || !["native_storage","trusted_import"].includes(row.origin)
      || typeof row.available !== "boolean" || typeof row.is_new !== "boolean") throw new Error("Invalid application summary.");
    keys.add(`${row.batch_id}/${row.upload_id}`);
  }
  if (keys.size !== v.applications.length || v.received_count !== keys.size
    || v.new_count !== v.applications.filter(r=>r.is_new).length
    || v.unavailable_count !== v.applications.filter(r=>!r.available).length) throw new Error("Invalid application summary.");
  return v;
}
export async function loadApplications(jobId: string, signal?: AbortSignal): Promise<Applications> {
  try {
  const response = await authenticatedFetch(`${BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/applications`, {signal});
  if (!response.ok) throw new Error("Applications unavailable. Try Refresh.");
  return validateApplications(await response.json(),jobId);
  } catch {throw new Error("Applications unavailable. Try Refresh.");}
}
export async function markApplicationsViewed(jobId: string, applications: ApplicationItem[]) {
  try {
  const response = await authenticatedFetch(`${BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/applications/viewed`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({applications:applications.map(({batch_id,upload_id})=>({batch_id,upload_id}))})});
  if (!response.ok) throw new Error("Viewed status was not confirmed. Refresh before trying again.");
  } catch {throw new Error("Viewed status was not confirmed. Refresh before trying again.");}
}
