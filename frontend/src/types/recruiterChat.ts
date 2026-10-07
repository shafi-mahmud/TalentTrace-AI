import type { JobDescriptionGenerationResponse } from "./jobDescription";

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

export type RecruiterChatResponse =
  | { status: "clarification"; intent: "create_job_description"; assistant_message: string; missing_fields: MissingField[] }
  | { status: "unsupported"; intent: "unsupported"; assistant_message: string }
  | { status: "jd_generated"; intent: "create_job_description"; assistant_message: string; job_description_result: JobDescriptionGenerationResponse };

export interface ChatMessage {
  role: "recruiter" | "assistant";
  text: string;
  missingFields?: MissingField[];
  jobDescriptionResult?: JobDescriptionGenerationResponse;
}
