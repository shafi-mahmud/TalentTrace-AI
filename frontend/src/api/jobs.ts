import { authenticatedFetch } from "./session.ts";
import { isScreeningSuggestions, isEmptyManualSuggestions, isReviewedSnapshot } from "./screening.ts";
import { isGenerationResponse } from "./jobDescriptions.ts";
import type { JobDescriptionGenerationResponse } from "../types/jobDescription";
import type { ReviewedJobSnapshot, ScreeningCriterion, ScreeningSuggestions } from "../types/screening";
import type { ScreeningSuggestionSource, WorkingCriteriaDraft } from "../types/recruiterChat";
import { isRecruiterChatResponse } from "./recruiterChat.ts";
import type { RecruiterChatResponse } from "../types/recruiterChat";
import { isScoringWeights } from "./scoring.ts";
import type { ScoringWeights } from "../types/screening";

const BASE = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export interface SavedJob {id: string; job_reference: string; job_title: string; revision: number;
  scoring_weights?: ScoringWeights;
  suggestions: ScreeningSuggestions; sources: ScreeningSuggestionSource[]; snapshot: ReviewedJobSnapshot | null;
  draft: JobDescriptionGenerationResponse | null; conversation_id: string | null;}
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;

export function isSavedJob(value: unknown): value is SavedJob {
  if (!value || typeof value !== "object") return false;
  const job = value as SavedJob;
  return typeof job.id === "string" && UUID.test(job.id) && /^TT-JOB-[A-F0-9]{16}$/.test(job.job_reference)
    && typeof job.job_title === "string" && Number.isInteger(job.revision) && job.revision > 0
    && (job.scoring_weights === undefined || isScoringWeights(job.scoring_weights))
    && (isScreeningSuggestions(job.suggestions) || (isEmptyManualSuggestions(job.suggestions)
      && job.draft === null && job.conversation_id === null && job.snapshot === null && Array.isArray(job.sources) && job.sources.length === 0))
    && job.suggestions.job_title === job.job_title
    && Array.isArray(job.sources) && job.sources.length <= job.suggestions.criteria.length
    && new Set(job.sources.map(s => s?.criterion_id)).size === job.sources.length
    && job.sources.every(s => s && typeof s.criterion_id === "string" && job.suggestions.criteria.some(c => c.criterion_id === s.criterion_id)
      && typeof s.evidence === "string" && !!s.evidence.trim() && s.evidence.length <= 1000 && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(s.evidence)
      && (s.source === "recruiter_input" ? s.citation_id == null && s.source_title == null :
        s.source === "company_policy" && typeof s.citation_id === "string" && /^policy:[0-9a-f]{32}:[0-9a-f]{16}:[0-9a-f]{16}:[0-9]{4,}$/.test(s.citation_id)
        && typeof s.source_title === "string" && s.source_title.length >= 2 && s.source_title.length <= 200 && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(s.source_title)))
    && (job.snapshot === null || (isReviewedSnapshot(job.snapshot) && job.snapshot.job_reference === job.job_reference && job.snapshot.job_title === job.job_title
      && job.snapshot.criteria.length === job.suggestions.criteria.length && job.snapshot.criteria.every((c, i) => {
        const expected = job.suggestions.criteria[i];
        return c.criterion_id === expected.criterion_id && c.description === expected.description && c.category === expected.category && c.is_hard === expected.is_hard;
      })))
    && (job.draft === null || isGenerationResponse(job.draft))
    && (job.conversation_id === null || (typeof job.conversation_id === "string" && UUID.test(job.conversation_id)));
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await authenticatedFetch(`${BASE}/api/v1${path}`, init);
  if (!response.ok) throw new Error(response.status === 409 ? "Job changed. Reload it and review the latest requirements." : "Job changes could not be confirmed.");
  return response.json();
}
export async function listJobs(): Promise<SavedJob[]> {
  const jobs = await request("/jobs");
  if (!Array.isArray(jobs) || !jobs.every(isSavedJob)) throw new Error("Saved jobs could not be validated.");
  return jobs;
}
export async function createJob(job_title: string): Promise<SavedJob> {
  const job = await request("/jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_title})});
  if (!isSavedJob(job)) throw new Error("Saved job could not be validated.");
  return job;
}
export async function saveCriteria(id: string, revision: number, criteria: ScreeningCriterion[], confirmed: boolean, weights?: ScoringWeights): Promise<SavedJob> {
  if (weights && !isScoringWeights(weights)) throw new Error("Weights must be whole percentages totaling 100.");
  const job = await request(`/jobs/${id}/criteria`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({revision, criteria, confirmed, ...(weights ? {weights} : {})})});
  if (!isSavedJob(job)) throw new Error("Saved requirements could not be validated.");
  return job;
}
export function workingJob(job: SavedJob): WorkingCriteriaDraft {
  return {draftId: job.id, jobReference: job.job_reference, revision: job.revision, savedSnapshot: job.snapshot,
    origin: job.draft ? "job_description" : "manual", suggestions: job.suggestions, sources: job.sources,
    weights: job.scoring_weights ?? {skill: 50, experience: 30, education: 20},
    criteria: job.suggestions.criteria.map(c => ({...c})), reviewed: job.snapshot !== null};
}

export async function listConversations(): Promise<{id: string; expires_at: string}[]> {
  const rows = await request("/conversations");
  if (!Array.isArray(rows) || !rows.every(row => row && typeof row.id === "string" && UUID.test(row.id) && typeof row.expires_at === "string"))
    throw new Error("Saved conversations could not be validated.");
  return rows;
}

export async function loadConversation(id: string): Promise<{id: string; ai_provider?:string; turns: {message: string; reply: RecruiterChatResponse}[]}> {
  if (!UUID.test(id)) throw new Error("Invalid conversation.");
  const body = await request(`/conversations/${id}`);
  if (!body || typeof body !== "object" || !("id" in body) || body.id !== id || !("turns" in body)
    || ('ai_provider' in body&&!['groq','ollama:qwen2.5:1.5b','ollama:smollm2:360m-instruct-q4_K_M'].includes(String(body.ai_provider)))
    || !Array.isArray(body.turns) || body.turns.length > 20 || !body.turns.every(turn => turn && typeof turn.message === "string"
      && turn.message.length <= 4000 && isRecruiterChatResponse(turn.reply) && turn.reply.conversation_id === id))
    throw new Error("Saved conversation could not be validated.");
  return body as {id: string; ai_provider?:string; turns: {message: string; reply: RecruiterChatResponse}[]};
}
