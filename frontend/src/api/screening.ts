import { authenticatedFetch } from "./session.ts";
import { isScoringBatch } from "./scoring.ts";
import { isGroundedAttribute } from "./candidateProfiles.ts";
import { isCvUploadResponse } from "./cvUploads.ts";
import type { CvUploadResponse } from "../types/cvUpload";
import type { BatchScreeningResponse, ReviewedJobSnapshot, ScreeningSuggestions } from "../types/screening";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const REFERENCE = /^TT-JOB-[A-F0-9]{16}$/;
const FAILURE = "Screening returned an invalid confirmation.";
function record(v: unknown): v is Record<string, unknown> { return v !== null && typeof v === "object" && !Array.isArray(v); }
function keys(v: unknown, names: string[]): v is Record<string, unknown> {
  return record(v) && Object.keys(v).length === names.length && names.every(name => Object.hasOwn(v, name));
}
function text(v: unknown, maximum: number): v is string {
  return typeof v === "string" && !!v.trim() && v.length <= maximum && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(v);
}
function criteria(v: unknown, maximum: number): boolean {
  return Array.isArray(v) && v.length >= 1 && v.length <= maximum && v.every(c =>
    keys(c, ["criterion_id", "description", "category", "is_hard"])
    && typeof c.criterion_id === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(c.criterion_id)
    && text(c.description, 500) && ["skill", "experience", "education"].includes(String(c.category)) && typeof c.is_hard === "boolean")
    && new Set(v.map(c => c.criterion_id.toLowerCase())).size === v.length;
}
export function isScreeningSuggestions(v: unknown): v is ScreeningSuggestions {
  return keys(v, ["job_title", "criteria"]) && text(v.job_title, 120) && criteria(v.criteria, 71);
}
export function isEmptyManualSuggestions(v: unknown): v is ScreeningSuggestions {
  return keys(v, ["job_title", "criteria"]) && text(v.job_title, 120) && Array.isArray(v.criteria) && v.criteria.length === 0;
}
export function isReviewedSnapshot(v: unknown): v is ReviewedJobSnapshot {
  return keys(v, ["job_title", "criteria", "job_reference", "criteria_confirmed"])
    && text(v.job_title, 120) && typeof v.job_reference === "string" && REFERENCE.test(v.job_reference)
    && v.criteria_confirmed === true && criteria(v.criteria, 50);
}
function same(a: unknown, b: unknown): boolean { return JSON.stringify(a) === JSON.stringify(b); }
function sameSnapshot(a: ReviewedJobSnapshot, b: ReviewedJobSnapshot): boolean {
  return a.job_reference === b.job_reference && a.job_title === b.job_title
    && a.criteria.length === b.criteria.length && a.criteria.every((c, i) => {
      const other = b.criteria[i];
      return c.criterion_id === other.criterion_id && c.category === other.category
        && c.description === other.description && c.is_hard === other.is_hard;
    });
}
function decision(value: unknown, snapshot: ReviewedJobSnapshot, uploadId: string): boolean {
  if (!keys(value, ["job_reference", "upload_id", "status", "screening_decision", "matching_result",
    "unmet_hard_requirement_ids", "ambiguous_hard_requirement_ids", "exclusion_reasons"])
    || value.job_reference !== snapshot.job_reference || value.upload_id !== uploadId) return false;
  const m = value.matching_result;
  if (!keys(m, ["job_reference", "upload_id", "parsing_status", "status", "requirement_context", "matches", "error_code", "screening_decision"])
    || m.job_reference !== snapshot.job_reference || m.upload_id !== uploadId || m.screening_decision !== null) return false;
  const context = m.requirement_context;
  if (!keys(context, ["skill_ids", "experience_ids", "education_ids", "hard_requirement_ids"])) return false;
  for (const category of ["skill", "experience", "education"] as const) {
    if (!same(context[`${category}_ids`], snapshot.criteria.filter(c => c.category === category).map(c => c.criterion_id))) return false;
  }
  if (!same(context.hard_requirement_ids, snapshot.criteria.filter(c => c.is_hard).map(c => c.criterion_id))) return false;
  if (!Array.isArray(m.matches)) return false;
  if (m.status !== "matching_complete") {
    return value.status === m.status && value.screening_decision === null && !m.matches.length
      && same(value.unmet_hard_requirement_ids, []) && same(value.ambiguous_hard_requirement_ids, []) && same(value.exclusion_reasons, [])
      && (m.status === "source_unavailable" ? ["source_unavailable", "parsing_failed"].includes(String(m.parsing_status)) && m.error_code === null
        : m.status === "matching_failed" && m.parsing_status === "parsed"
          && ["semantic_not_configured", "semantic_provider_failed", "invalid_semantic_response", "semantic_input_limit"].includes(String(m.error_code)));
  }
  if (value.status !== "decision_complete" || m.parsing_status !== "parsed" || m.error_code !== null || m.matches.length !== snapshot.criteria.length) return false;
  for (const [index, match] of m.matches.entries()) {
    if (!keys(match, ["criterion_id", "match_status", "match_method", "explanation", "evidence"])
      || match.criterion_id !== snapshot.criteria[index].criterion_id || !["supported", "not_found", "ambiguous"].includes(String(match.match_status))
      || !["deterministic", "semantic"].includes(String(match.match_method)) || !text(match.explanation, 300)
      || !Array.isArray(match.evidence) || match.evidence.length > 8
      || (match.match_status === "not_found" ? match.evidence.length !== 0 : match.evidence.length === 0)
      || new Set(match.evidence.map(e => record(e) ? e.fact_id : null)).size !== match.evidence.length
      || !match.evidence.every(e => keys(e, ["fact_id", "value", "source"]) && typeof e.fact_id === "string"
        && /^fact:[0-9]{4}$/.test(e.fact_id) && isGroundedAttribute({value: e.value, source: e.source}))) return false;
  }
  const missing = m.matches.filter((match, i) => snapshot.criteria[i].is_hard && match.match_status === "not_found").map(match => match.criterion_id);
  const ambiguous = m.matches.filter((match, i) => snapshot.criteria[i].is_hard && match.match_status === "ambiguous").map(match => match.criterion_id);
  const outcome = missing.length ? "excluded" : ambiguous.length ? "insufficient_evidence" : "eligible";
  return value.screening_decision === outcome && same(value.unmet_hard_requirement_ids, missing)
    && same(value.ambiguous_hard_requirement_ids, ambiguous) && Array.isArray(value.exclusion_reasons)
    && value.exclusion_reasons.length === missing.length && value.exclusion_reasons.every((reason, i) =>
      keys(reason, ["criterion_id", "code", "message"]) && reason.criterion_id === missing[i]
      && reason.code === "hard_requirement_not_demonstrated" && reason.message === "Hard requirement was not demonstrated in the parsed CV.");
}
export function isBatchScreeningResponse(v: unknown): v is BatchScreeningResponse {
  if (!(keys(v, ["status", "job_reference", "batch_id", "snapshot", "processed_count", "candidates", "ranking"])
      || keys(v, ["status", "job_reference", "batch_id", "snapshot", "processed_count", "candidates", "ranking", "scoring"]))
    || v.status !== "processed" || typeof v.batch_id !== "string" || !UUID.test(v.batch_id)
    || !isReviewedSnapshot(v.snapshot) || v.job_reference !== v.snapshot.job_reference
    || !Array.isArray(v.candidates) || v.candidates.length < 1 || v.candidates.length > 20 || v.processed_count !== v.candidates.length) return false;
  const snapshot = v.snapshot;
  if (!(new Set(v.candidates.map(c => record(c) ? c.upload_id : null)).size === v.candidates.length
    && v.candidates.every(c => keys(c, ["upload_id", "result", "error_code", "overall_coverage"]) && typeof c.upload_id === "string" && UUID.test(c.upload_id)
      && (c.result === null ? c.error_code === "screening_processing_failed" : c.error_code === null && decision(c.result, snapshot, c.upload_id))))) return false;
  // Verify server ranks against validated evidence; never trust a client/provider score.
  const candidates = v.candidates as BatchScreeningResponse["candidates"];
  if (!candidates.every(c => {
    const statuses = c.result?.matching_result.matches.map(m => m.match_status) ?? [];
    const coverage = !c.result || c.result.status !== "decision_complete" ? "not_evaluated"
      : statuses.includes("ambiguous") ? "uncertain"
      : statuses.every(s => s === "supported") ? "met"
      : statuses.every(s => s === "not_found") ? "unmet" : "partially_met";
    return c.overall_coverage === coverage;
  })) return false;
  const expected = candidates.filter(c => c.result?.status === "decision_complete" && c.result.screening_decision === "eligible").map(c => {
    const matches = c.result!.matching_result.matches;
    return {upload_id: c.upload_id, supported_count: matches.filter(m => m.match_status === "supported").length,
      ambiguous_count: matches.filter(m => m.match_status === "ambiguous").length,
      not_found_count: matches.filter(m => m.match_status === "not_found").length, total_requirements: snapshot.criteria.length};
  }).sort((a, b) => b.supported_count - a.supported_count || (a.upload_id < b.upload_id ? -1 : a.upload_id > b.upload_id ? 1 : 0));
  if (!Array.isArray(v.ranking) || v.ranking.length !== expected.length) return false;
  const ranking = v.ranking;
  return expected.every((row, i) => {
    const entry = ranking[i];
    const rank = 1 + expected.filter(other => other.supported_count > row.supported_count).length;
    const tied = expected.filter(other => other.supported_count === row.supported_count).length > 1;
    return keys(entry, ["upload_id", "rank", "tied", "supported_count", "ambiguous_count", "not_found_count", "total_requirements"])
      && entry.upload_id === row.upload_id && entry.rank === rank && entry.tied === tied
      && entry.supported_count === row.supported_count && entry.ambiguous_count === row.ambiguous_count
      && entry.not_found_count === row.not_found_count && entry.total_requirements === row.total_requirements;
  }) && (v.scoring == null || isScoringBatch(v.scoring, v as unknown as BatchScreeningResponse));
}
export async function screenCvBatch(batch: CvUploadResponse, snapshot: ReviewedJobSnapshot, revision?: number): Promise<BatchScreeningResponse> {
  if (!isCvUploadResponse(batch) || !isReviewedSnapshot(snapshot) || batch.job_reference !== snapshot.job_reference) {
    throw new Error("Confirm criteria for this uploaded job reference before screening.");
  }
  return screenStoredBatch({job_reference:batch.job_reference,batch_id:batch.batch_id,upload_ids:batch.files.map(f=>f.upload_id)},snapshot,revision);
}

export interface StoredBatchIdentity {job_reference:string;batch_id:string;upload_ids:string[];job_id?:string;}
export async function screenStoredBatch(batch:StoredBatchIdentity,snapshot:ReviewedJobSnapshot,revision?:number,reviewToken?:string):Promise<BatchScreeningResponse>{
  if(!isReviewedSnapshot(snapshot) || batch.job_reference!==snapshot.job_reference || !UUID.test(batch.batch_id)
    || batch.upload_ids.length<1 || batch.upload_ids.length>20 || !batch.upload_ids.every(id=>UUID.test(id)) || new Set(batch.upload_ids).size!==batch.upload_ids.length)throw Error(FAILURE);
  let response: Response;
  try {
    response = await authenticatedFetch(`${API_BASE_URL}/api/v1/cv-uploads/${batch.job_reference}/${batch.batch_id}/screen`, {
      method: "POST", headers: {"Content-Type": "application/json", ...(revision ? {"X-TalentTrace-Job-Revision": String(revision)} : {}),
        ...(reviewToken ? {"X-TalentTrace-Imported-Review":reviewToken} : {})}, body: JSON.stringify(snapshot),
    });
  } catch { throw new Error("Screening was not confirmed. Check saved results before retrying; provider calls may repeat."); }
  if (!response.ok) throw new Error(response.status === 409 ? "Stored batch or criteria changed. Reload and review before screening."
    : response.status === 503 ? "Candidate profile extraction is not configured." : "Batch screening could not be completed. Check saved results before retrying.");
  const body: unknown = await response.json().catch(() => null);
  if (!isBatchScreeningResponse(body) || body.job_reference !== batch.job_reference || body.batch_id !== batch.batch_id
    || !sameSnapshot(body.snapshot, snapshot) || body.processed_count !== batch.upload_ids.length
    || body.candidates.some(c => !batch.upload_ids.includes(c.upload_id))
    || (batch.job_id && (!body.scoring || body.scoring.job_id!==batch.job_id || body.scoring.criteria_revision!==revision))) throw new Error(FAILURE);
  return body;
}
