import type {
  FieldErrors,
  JobDescriptionField,
  JobDescriptionGenerationRequest,
  JobDescriptionGenerationResponse,
} from "../types/jobDescription";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const GENERATION_FAILURE =
  "Job description generation could not be completed. Please try again.";

export class JobDescriptionApiError extends Error {
  readonly fieldErrors: FieldErrors;

  constructor(message: string, fieldErrors: FieldErrors = {}) {
    super(message);
    this.name = "JobDescriptionApiError";
    this.fieldErrors = fieldErrors;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isGenerationResponse(
  value: unknown,
): value is JobDescriptionGenerationResponse {
  if (!isRecord(value) || !isRecord(value.job_description)) return false;
  const draft = value.job_description;
  return (
    value.status === "draft" &&
    value.human_review_required === true &&
    value.provider === "groq" &&
    value.retrieval_mode === "deterministic_lexical_demo" &&
    typeof value.model === "string" &&
    typeof draft.title === "string" &&
    typeof draft.summary === "string" &&
    isStringArray(draft.responsibilities) &&
    isStringArray(draft.required_skills) &&
    isStringArray(draft.preferred_skills) &&
    isStringArray(draft.qualifications) &&
    isStringArray(draft.policy_citation_ids) &&
    Array.isArray(value.grounding_citations) &&
    value.grounding_citations.length > 0 &&
    value.grounding_citations.every(
      (citation: unknown) =>
        isRecord(citation) &&
        typeof citation.citation_id === "string" &&
        typeof citation.source_title === "string" &&
        Array.isArray(citation.heading_paths) &&
        citation.heading_paths.every(isStringArray),
    )
  );
}

const FIELD_NAMES: Record<JobDescriptionField, string> = {
  job_title: "Job title",
  role_summary: "Role summary",
  responsibilities: "Responsibilities",
  required_skills: "Required skills",
  work_arrangement: "Work arrangement",
  location: "Location",
};

// Display only our own messages, never arbitrary text supplied in an error body.
const VALIDATION_MESSAGES: Record<string, string> = {
  missing: "This field is required.",
  string_too_short: "Please add more detail.",
  string_too_long: "This entry is too long. Please shorten it.",
  too_short: "Please enter at least one item.",
  too_long: "There are too many items. Please shorten the list.",
  enum: "Please choose one of the available options.",
  value_error: "Check for duplicate entries or unsupported characters.",
};

function validationFeedback(body: unknown): FieldErrors {
  const errors: FieldErrors = {};
  if (!isRecord(body) || !Array.isArray(body.detail)) return errors;
  for (const error of body.detail) {
    if (!isRecord(error) || !Array.isArray(error.loc)) continue;
    const field = error.loc[1];
    if (typeof field !== "string" || !Object.hasOwn(FIELD_NAMES, field)) continue;
    const knownField = field as JobDescriptionField;
    const message =
      typeof error.type === "string" && Object.hasOwn(VALIDATION_MESSAGES, error.type)
        ? VALIDATION_MESSAGES[error.type]
        : undefined;
    errors[knownField] = message ?? "Please check this field.";
  }
  return errors;
}

export async function generateJobDescription(
  request: JobDescriptionGenerationRequest,
): Promise<JobDescriptionGenerationResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/job-descriptions/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new JobDescriptionApiError("Cannot reach the TalentTrace AI backend.");
  }

  if (response.status === 422) {
    const body: unknown = await response.json().catch(() => null);
    const fieldErrors = validationFeedback(body);
    throw new JobDescriptionApiError(
      Object.keys(fieldErrors).length
        ? "Please check the highlighted fields and try again."
        : "Please check your entries and try again.",
      fieldErrors,
    );
  }
  if (!response.ok) {
    const message =
      response.status === 503
        ? "Job description generation is not configured."
        : response.status === 504
          ? "Job description generation timed out. Please try again."
          : GENERATION_FAILURE;
    throw new JobDescriptionApiError(message);
  }

  const body: unknown = await response.json().catch(() => null);
  if (!isGenerationResponse(body)) {
    throw new JobDescriptionApiError(GENERATION_FAILURE);
  }
  return body;
}
