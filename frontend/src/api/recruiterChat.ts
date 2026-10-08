import { isGenerationResponse } from "./jobDescriptions.ts";
import { isScreeningSuggestions } from "./screening.ts";
import { MISSING_FIELD_LABELS } from "../types/recruiterChat.ts";
import type { RecruiterChatResponse, PublishingContext } from "../types/recruiterChat";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const FAILURE = "Recruiter chat could not be completed.";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class RecruiterChatRequestError extends Error {
  readonly uncertain: boolean;
  readonly retryable: boolean;

  constructor(message: string, uncertain: boolean, retryable: boolean) {
    super(message);
    this.uncertain = uncertain;
    this.retryable = retryable;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isRecruiterChatResponse(value: unknown): value is RecruiterChatResponse {
  if (!isRecord(value) || typeof value.assistant_message !== "string"
      || !value.assistant_message.trim() || value.assistant_message.length > 600
      || typeof value.conversation_id !== "string" || !UUID.test(value.conversation_id)) return false;
  if (value.status === "unsupported") return value.intent === "unsupported";
  if (value.intent !== "create_job_description") return false;
  if (value.status === "draft_unchanged") return true;
  if (value.status === "jd_generated") {
    if (typeof value.draft_id !== "string" || !UUID.test(value.draft_id)
        || !isGenerationResponse(value.job_description_result)
        || !isScreeningSuggestions(value.screening_suggestions)
        || !isPublishingContext(value.publishing_context)
        || !Array.isArray(value.screening_suggestion_sources)) return false;
    const suggestions = value.screening_suggestions;
    return value.screening_suggestion_sources.length <= suggestions.criteria.length
      && new Set(value.screening_suggestion_sources.map(source => isRecord(source) ? source.criterion_id : null)).size === value.screening_suggestion_sources.length
      && value.screening_suggestion_sources.every(source => isRecord(source)
        && Object.keys(source).length === 3 && Object.hasOwn(source, "criterion_id") && Object.hasOwn(source, "source") && Object.hasOwn(source, "evidence")
        && typeof source.criterion_id === "string" && suggestions.criteria.some(c => c.criterion_id === source.criterion_id)
        && source.source === "recruiter_input" && typeof source.evidence === "string" && !!source.evidence.trim() && source.evidence.length <= 1000
        && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(source.evidence));
  }
  return value.status === "clarification" && Array.isArray(value.missing_fields)
    && value.missing_fields.length > 0 && value.missing_fields.length <= Object.keys(MISSING_FIELD_LABELS).length
    && value.missing_fields.every((field) => typeof field === "string" && Object.hasOwn(MISSING_FIELD_LABELS, field));
}

export async function sendRecruiterMessage(message: string, conversationId?: string): Promise<RecruiterChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/recruiter-chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, ...(conversationId ? {conversation_id: conversationId} : {}) }),
    });
  } catch {
    throw new RecruiterChatRequestError("Cannot reach the TalentTrace AI backend. The request may have been received.", true, true);
  }
  if (!response.ok) {
    // Never display arbitrary provider/server errors or returned request text.
    const message = response.status === 422
      ? "Use a plain-text job instruction of up to 4000 characters, without candidate information or unsafe control characters."
      : response.status === 503 ? "Recruiter chat is not configured."
      : response.status === 504 ? "Recruiter chat timed out."
      : response.status === 409 ? "This conversation expired or reached its limit. Start a new chat." : FAILURE;
    throw new RecruiterChatRequestError(message, response.status >= 500, response.status !== 409 && response.status !== 422);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!isRecruiterChatResponse(body)) throw new RecruiterChatRequestError(FAILURE, true, true);
  return body;
}


export function isValidRecruiterMessage(message: string): boolean {
  const text = message.trim();
  return text.length > 0 && text.length <= 4000
    && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(text.replace(/[\r\n\t]/g, ""));
}


function isPublishingContext(value: unknown): value is PublishingContext {
  if (!isRecord(value) || Object.keys(value).some(key => !["location", "employment_type", "work_arrangement"].includes(key))) return false;
  return (value.location == null || (typeof value.location === "string" && value.location.length <= 150))
    && (value.employment_type == null || ["full_time", "part_time", "contract", "internship", "temporary"].includes(String(value.employment_type)))
    && (value.work_arrangement == null || ["on_site", "remote", "hybrid"].includes(String(value.work_arrangement)));
}
