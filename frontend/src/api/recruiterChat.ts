import { isGenerationResponse } from "./jobDescriptions.ts";
import { MISSING_FIELD_LABELS } from "../types/recruiterChat.ts";
import type { RecruiterChatResponse } from "../types/recruiterChat";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const FAILURE = "Recruiter chat could not be completed. Please try again.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isRecruiterChatResponse(value: unknown): value is RecruiterChatResponse {
  if (!isRecord(value) || typeof value.assistant_message !== "string"
      || !value.assistant_message.trim() || value.assistant_message.length > 600) return false;
  if (value.status === "unsupported") return value.intent === "unsupported";
  if (value.intent !== "create_job_description") return false;
  if (value.status === "jd_generated") return isGenerationResponse(value.job_description_result);
  return value.status === "clarification" && Array.isArray(value.missing_fields)
    && value.missing_fields.length > 0 && value.missing_fields.length <= Object.keys(MISSING_FIELD_LABELS).length
    && value.missing_fields.every((field) => typeof field === "string" && Object.hasOwn(MISSING_FIELD_LABELS, field));
}

export async function sendRecruiterMessage(message: string): Promise<RecruiterChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/recruiter-chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  } catch {
    throw new Error("Cannot reach the TalentTrace AI backend.");
  }
  if (!response.ok) {
    // Never display arbitrary provider/server errors or returned request text.
    throw new Error(response.status === 422
      ? "Use a plain-text job instruction of up to 4000 characters, without candidate information or unsafe control characters."
      : response.status === 503 ? "Recruiter chat is not configured."
      : response.status === 504 ? "Recruiter chat timed out. Please try again." : FAILURE);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!isRecruiterChatResponse(body)) throw new Error(FAILURE);
  return body;
}


export function isValidRecruiterMessage(message: string): boolean {
  const text = message.trim();
  return text.length > 0 && text.length <= 4000
    && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(text.replace(/[\r\n\t]/g, ""));
}
