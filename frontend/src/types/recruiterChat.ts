import type { JobDescriptionGenerationResponse } from "./jobDescription";
import type { ScreeningCriterion, ScreeningSuggestions, ReviewedJobSnapshot } from "./screening";

export const MISSING_FIELD_LABELS = {
  job_title: "Job title",
  role_summary: "Role purpose or summary",
  responsibilities: "Responsibilities",
  required_skills: "Required skills",
  department: "Department",
  employment_type: "Employment type",
  work_arrangement: "Work arrangement",
  location: "Location",
  seniority_level: "Seniority level",
  preferred_skills: "Preferred skills",
  minimum_experience_years: "Minimum experience years",
  education_requirements: "Education requirements",
} as const;

export type MissingField = keyof typeof MISSING_FIELD_LABELS;

export interface PublishingContext {
  location?: string | null;
  employment_type?: "full_time" | "part_time" | "contract" | "internship" | "temporary" | null;
  work_arrangement?: "on_site" | "remote" | "hybrid" | null;
}
export type AutomaticDestination = "discord" | "telegram";
export interface PublicationResult { destination: AutomaticDestination; status: "published"; external_id: string; }
export type PublicationState = {status: "idle" | "loading"} | {status: "success"; result: PublicationResult} | {status: "failed"; message: string};
export interface ScreeningSuggestionSource { criterion_id: string; source: "recruiter_input" | "company_policy"; evidence: string; citation_id?: string | null; source_title?: string | null; }
export interface WorkingCriteriaDraft {
  draftId: string;
  jobReference?: string;
  revision?: number;
  weights?: import("./screening").ScoringWeights;
  savedSnapshot?: ReviewedJobSnapshot | null;
  origin?: "job_description" | "manual";
  suggestions: ScreeningSuggestions;
  sources: ScreeningSuggestionSource[];
  criteria: ScreeningCriterion[];
  reviewed: boolean;
}

export type RecruiterChatResponse =
  | { status: "clarification"; intent: "create_job_description"; conversation_id: string; assistant_message: string; missing_fields: MissingField[] }
  | { status: "unsupported"; intent: "unsupported"; conversation_id: string; assistant_message: string }
  | { status: "draft_unchanged"; intent: "create_job_description"; conversation_id: string; assistant_message: string }
  | { status: "jd_generated"; intent: "create_job_description"; conversation_id: string; draft_id: string; job_reference?: string | null; job_revision?: number; assistant_message: string; job_description_result: JobDescriptionGenerationResponse; publishing_context: PublishingContext; screening_suggestions: ScreeningSuggestions; screening_suggestion_sources: ScreeningSuggestionSource[] };

export interface ChatMessage {
  role: "recruiter" | "assistant";
  text: string;
  localMessageId?: string;
  sendState?: "sending" | "failed" | "uncertain" | "sent";
  sendError?: string;
  retryAvailable?: boolean;
  missingFields?: MissingField[];
  jobDescriptionResult?: JobDescriptionGenerationResponse;
  publishingContext?: PublishingContext;
  publication?: PublicationState;
  publications?: Partial<Record<AutomaticDestination,PublicationState>>;
  sourceInstruction?: string;
  screeningSuggestions?: ScreeningSuggestions;
  conversationId?: string;
  draftId?: string;
  jobReference?: string;
  jobRevision?: number;
  screeningSuggestionSources?: ScreeningSuggestionSource[];
}
