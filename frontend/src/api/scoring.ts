import { authenticatedFetch } from "./session.ts";
import type { BatchScreeningResponse, ScoringBatch, ScoringWeights } from "../types/screening";

function keys(v: unknown, names: string[]): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v, n));
}
export function isScoringWeights(v: unknown): v is ScoringWeights {
  return keys(v, ["skill", "experience", "education"]) && [v.skill, v.experience, v.education].every(n => typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= 100)
    && Number(v.skill) + Number(v.experience) + Number(v.education) === 100;
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
// All ratios are integer fractions; round half-up without floating point drift.
const rounded = (n: number, d: number) => Math.floor((n * 200 + d) / (2 * d)) / 100;

export function isAIProvenance(value:unknown):boolean {
 return value==null || keys(value,['provider','model','external_processing_confirmed'])
  && ['groq','ollama'].includes(String(value.provider)) && typeof value.model==='string'
  && /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$/.test(value.model)&&!value.model.includes('://')
  && value.external_processing_confirmed===(value.provider==='groq');
}

export function isScoringBatch(value: unknown, batch: BatchScreeningResponse): value is ScoringBatch {
  const provenanceField=value&&typeof value==='object'&&Object.hasOwn(value,'ai_provenance')?['ai_provenance']:[];
  if (!keys(value, ["job_id", "job_reference", "batch_id", "criteria_revision", "scoring_version", "weights", "candidates", "ranking",...provenanceField])
    || !isAIProvenance(value.ai_provenance)
    || typeof value.job_id !== "string" || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.job_id)
    || value.job_reference !== batch.job_reference || value.batch_id !== batch.batch_id || value.scoring_version !== "f2-coverage-v1"
    || !Number.isInteger(value.criteria_revision) || Number(value.criteria_revision) < 1 || !isScoringWeights(value.weights)
    || !Array.isArray(value.candidates) || value.candidates.length !== batch.candidates.length || !Array.isArray(value.ranking)) return false;
  const weights = value.weights;
  if (new Set(value.candidates.map(c => c?.upload_id)).size !== batch.candidates.length) return false;
  for (const score of value.candidates) {
    if (!keys(score, ["job_reference", "upload_id", "screening_decision", "status", "reason", "weights", "score", "dimensions"]) || !same(score.weights, weights)) return false;
    const item = batch.candidates.find(c => c.upload_id === score.upload_id);
    if (!item || score.job_reference !== batch.job_reference || score.screening_decision !== (item.result?.screening_decision ?? null)) return false;
    const result = item.result;
    const categories = ["skill", "experience", "education"] as const;
    const groups = categories.map(category => result?.matching_result.matches.filter(m => batch.snapshot.criteria.some(c => c.criterion_id === m.criterion_id && c.category === category)) ?? []);
    const reason = !result ? "processing_failed" : result.status !== "decision_complete" ? "screening_incomplete"
      : result.screening_decision !== "eligible" ? "not_eligible"
      : groups.some((g, i) => weights[categories[i]] > 0 && g.some(m => m.match_status === "ambiguous")) ? "uncertain_evidence"
      : groups.some((g, i) => weights[categories[i]] > 0 && !g.length) ? "missing_dimension_criteria" : null;
    if (reason) {
      if (score.status !== "not_evaluated" || score.reason !== reason || score.score !== null || !same(score.dimensions, [])) return false;
      continue;
    }
    if (score.status !== "scored" || score.reason !== null || !Array.isArray(score.dimensions) || score.dimensions.length !== 3) return false;
    let numerator = 0, denominator = 1;
    for (const [i, matches] of groups.entries()) {
      const dimension = score.dimensions[i], category = categories[i], supported = matches.filter(m => m.match_status === "supported").length;
      const weight = weights[category];
      if (!keys(dimension, ["category", "weight", "supported_count", "total_requirements", "coverage_percent", "weighted_points", "matches"])
        || dimension.category !== category || dimension.weight !== weight || dimension.supported_count !== supported || dimension.total_requirements !== matches.length
        || !same(dimension.matches, matches) || dimension.coverage_percent !== (matches.length ? rounded(100 * supported, matches.length) : null)
        || dimension.weighted_points !== (matches.length ? rounded(weight * supported, matches.length) : 0)) return false;
      if (matches.length) {numerator = numerator * matches.length + weight * supported * denominator; denominator *= matches.length;}
    }
    if (score.score !== rounded(numerator, denominator)) return false;
  }
  const rows = (value as unknown as ScoringBatch).candidates.filter(c => c.status === "scored").sort((a, b) => b.score! - a.score! || a.upload_id.localeCompare(b.upload_id));
  return value.ranking.length === rows.length && rows.every((row, i) => {
    const entry = (value.ranking as unknown[])[i];
    return keys(entry, ["upload_id", "score", "rank", "tied"]) && entry.upload_id === row.upload_id && entry.score === row.score
      && entry.rank === 1 + rows.filter(other => other.score! > row.score!).length
      && entry.tied === (rows.filter(other => other.score === row.score).length > 1);
  });
}

export async function loadScores(jobId: string, revision: number, batch: BatchScreeningResponse): Promise<ScoringBatch> {
  const base = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
  const response = await authenticatedFetch(`${base}/api/v1/jobs/${jobId}/batches/${batch.batch_id}/scores`);
  if (!response.ok) throw new Error(response.status === 409 ? "Job changed. Review criteria and weights again." : "Saved scores could not be loaded.");
  const value: unknown = await response.json().catch(() => null);
  if (!isScoringBatch(value, batch) || value.job_id !== jobId || value.criteria_revision !== revision) throw new Error("Saved scores could not be validated.");
  return value;
}
