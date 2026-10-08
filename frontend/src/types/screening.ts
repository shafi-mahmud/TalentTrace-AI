import type { CandidateAttribute } from "./candidateProfile";

export interface ScreeningCriterion {
  criterion_id: string;
  description: string;
  category: "skill" | "experience" | "education";
  is_hard: boolean;
}
export interface ScreeningSuggestions { job_title: string; criteria: ScreeningCriterion[]; }
export interface ReviewedJobSnapshot extends ScreeningSuggestions {
  job_reference: string;
  criteria_confirmed: true;
}
export interface RequirementMatch {
  criterion_id: string;
  match_status: "supported" | "not_found" | "ambiguous";
  match_method: "deterministic" | "semantic";
  explanation: string;
  evidence: (CandidateAttribute & {fact_id: string})[];
}
export interface ScreeningDecision {
  job_reference: string;
  upload_id: string;
  status: "decision_complete" | "source_unavailable" | "matching_failed";
  screening_decision: "eligible" | "excluded" | "insufficient_evidence" | null;
  matching_result: {
    job_reference: string; upload_id: string;
    parsing_status: "parsed" | "source_unavailable" | "parsing_failed";
    status: "matching_complete" | "source_unavailable" | "matching_failed";
    requirement_context: {skill_ids: string[]; experience_ids: string[]; education_ids: string[]; hard_requirement_ids: string[]};
    matches: RequirementMatch[];
    error_code: "semantic_not_configured" | "semantic_provider_failed" | "invalid_semantic_response" | "semantic_input_limit" | null;
    screening_decision: null;
  };
  unmet_hard_requirement_ids: string[];
  ambiguous_hard_requirement_ids: string[];
  exclusion_reasons: {criterion_id: string; code: "hard_requirement_not_demonstrated"; message: string}[];
}
export interface BatchScreeningResponse {
  status: "processed"; job_reference: string; batch_id: string;
  snapshot: ReviewedJobSnapshot; processed_count: number;
  candidates: {upload_id: string; result: ScreeningDecision | null; error_code: "screening_processing_failed" | null}[];
}
