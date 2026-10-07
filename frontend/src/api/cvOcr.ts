import type { CvExtractionResponse } from "../types/cvExtraction";
import type { CvOcrResponse } from "../types/cvOcr";
import { isCvExtractionResponse } from "./cvExtraction.ts";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function count(value: unknown, maximum: number) {
  return Number.isInteger(value) && Number(value) >= 0 && Number(value) <= maximum;
}

export function isCvOcrResponse(value: unknown): value is CvOcrResponse {
  if (!record(value) || Object.keys(value).some(key => !["status", "job_reference", "batch_id", "attempted_count", "files"].includes(key))) return false;
  return value.status === "processed" && typeof value.job_reference === "string" && /^TT-JOB-[A-F0-9]{16}$/.test(value.job_reference)
    && typeof value.batch_id === "string" && UUID.test(value.batch_id)
    && count(value.attempted_count, 20) && Array.isArray(value.files) && value.files.length === value.attempted_count
    && new Set(value.files.map(file => record(file) ? file.upload_id : null)).size === value.files.length
    && value.files.every(file => record(file) && Object.keys(file).every(key => ["upload_id", "ocr_status", "text_char_count", "page_count", "ocr_page_count"].includes(key))
      && typeof file.upload_id === "string" && UUID.test(file.upload_id)
      && (file.ocr_status === "ocr_extracted" || file.ocr_status === "ocr_failed")
      && count(file.text_char_count, 500000) && count(file.page_count, 200) && Number(file.page_count) > 0
      && count(file.ocr_page_count, 25) && Number(file.ocr_page_count) <= Number(file.page_count)
      && (file.ocr_status !== "ocr_extracted" || (Number(file.text_char_count) > 0 && Number(file.ocr_page_count) > 0 && Number(file.page_count) <= 25)));
}

export async function runCvOcr(extraction: CvExtractionResponse): Promise<CvOcrResponse> {
  if (!isCvExtractionResponse(extraction)) throw new Error("A valid extracted batch is required.");
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/cv-uploads/${extraction.job_reference}/${extraction.batch_id}/ocr`, {method: "POST"});
  } catch {
    throw new Error("OCR could not be confirmed. Your uploaded files are unchanged.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(response.status === 503 && record(body) && body.code === "ocr_not_configured"
    ? "OCR is not configured on this server." : "OCR could not be completed. Your uploaded files are unchanged.");
  const eligible = extraction.files.filter(file => file.file_type === "pdf" && file.extraction_status === "ocr_required");
  if (!isCvOcrResponse(body) || body.job_reference !== extraction.job_reference || body.batch_id !== extraction.batch_id
    || body.attempted_count !== eligible.length || body.files.some(file => !eligible.some(original => original.upload_id === file.upload_id && original.source_unit_count === file.page_count))) {
    throw new Error("OCR returned an invalid confirmation.");
  }
  return body;
}
