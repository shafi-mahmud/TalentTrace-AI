export type WorkArrangement = "on_site" | "hybrid" | "remote";

export interface JobDescriptionGenerationRequest {
  job_title: string;
  role_summary: string;
  responsibilities: string[];
  required_skills: string[];
  work_arrangement?: WorkArrangement;
  location?: string;
}

export type JobDescriptionField = keyof JobDescriptionGenerationRequest;
export type FieldErrors = Partial<Record<JobDescriptionField, string>>;

export interface GeneratedJobDescriptionDraft {
  title: string;
  summary: string;
  responsibilities: string[];
  required_skills: string[];
  preferred_skills: string[];
  qualifications: string[];
  policy_citation_ids: string[];
}

export interface PolicyGroundingCitation {
  citation_id: string;
  source_title: string;
  heading_paths: string[][];
}

export interface JobDescriptionGenerationResponse {
  status: "draft";
  human_review_required: true;
  retrieval_mode: "deterministic_lexical_demo";
  provider: "groq";
  model: string;
  job_description: GeneratedJobDescriptionDraft;
  grounding_citations: PolicyGroundingCitation[];
}
