import type { CvExtractionResponse } from "../types/cvExtraction";
import type { CvUploadResponse } from "../types/cvUpload";
import { isCvUploadResponse } from "./cvUploads.ts";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function boundedCount(value: unknown, maximum: number) {
  return Number.isInteger(value) && Number(value) >= 0 && Number(value) <= maximum;
}

export function isCvExtractionResponse(value: unknown): value is CvExtractionResponse {
  if (!record(value) || Object.keys(value).some(key => !["status", "job_reference", "batch_id", "processed_count", "files"].includes(key))) return false;
  return value.status === "processed" && typeof value.job_reference === "string" && /^TT-JOB-[A-F0-9]{16}$/.test(value.job_reference)
    && typeof value.batch_id === "string" && UUID.test(value.batch_id)
    && boundedCount(value.processed_count, 20) && Number(value.processed_count) > 0
    && Array.isArray(value.files) && value.files.length === value.processed_count
    && new Set(value.files.map(file => record(file) ? file.upload_id : null)).size === value.files.length
    && value.files.every(file => record(file) && Object.keys(file).every(key => ["upload_id", "file_type", "extraction_status", "text_char_count", "source_unit_count", "ocr_recommended"].includes(key))
      && typeof file.upload_id === "string" && UUID.test(file.upload_id)
      && (file.file_type === "pdf" || file.file_type === "docx")
      && ["text_extracted", "ocr_required", "extraction_failed"].includes(String(file.extraction_status)) && typeof file.extraction_status === "string"
      && boundedCount(file.text_char_count, 500000) && boundedCount(file.source_unit_count, file.file_type === "pdf" ? 200 : 10000)
      && file.ocr_recommended === (file.extraction_status === "ocr_required")
      && (file.extraction_status !== "ocr_required" || file.file_type === "pdf")
      && (file.extraction_status !== "text_extracted" || (Number(file.text_char_count) > 0 && Number(file.source_unit_count) > 0)));
}

export async function extractCvs(batch: CvUploadResponse): Promise<CvExtractionResponse> {
  if (!isCvUploadResponse(batch)) throw new Error("A valid uploaded batch is required.");
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/cv-uploads/${batch.job_reference}/${batch.batch_id}/extract`, {method: "POST"});
  } catch {
    throw new Error("Text extraction could not be confirmed. Your uploaded files are unchanged.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(response.status === 404 ? "The uploaded batch was not found." : "Text extraction could not be completed. Your uploaded files are unchanged.");
  if (!isCvExtractionResponse(body) || body.job_reference !== batch.job_reference || body.batch_id !== batch.batch_id
    || body.processed_count !== batch.accepted_count || body.files.some(file => !batch.files.some(upload => upload.upload_id === file.upload_id && upload.file_type === file.file_type))) {
    throw new Error("Text extraction returned an invalid confirmation.");
  }
  return body;
}
