import type { CvUploadResponse } from "../types/cvUpload";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const MIB = 1024 * 1024;
const REFERENCE = /^TT-JOB-[A-F0-9]{16}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function validateCvSelection(jobReference: string, files: readonly Pick<File, "name" | "size">[]): string | null {
  if (!isValidJobReference(jobReference)) return "Enter the TT-JOB reference shown in the published job.";
  if (files.length < 1 || files.length > 20) return "Select between 1 and 20 PDF/DOCX files.";
  if (files.some(file => !/\.(pdf|docx)$/i.test(file.name))) return "Only PDF and DOCX files are supported.";
  if (files.some(file => file.size <= 0 || file.size > 10 * MIB)) return "Each file must be nonempty and no larger than 10 MiB.";
  if (files.reduce((sum, file) => sum + file.size, 0) > 100 * MIB) return "The batch must be no larger than 100 MiB.";
  return null;
}

export function isValidJobReference(value: string): boolean {
  return REFERENCE.test(value.trim());
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isCvUploadResponse(value: unknown): value is CvUploadResponse {
  if (!record(value) || Object.keys(value).some(key => !["status", "job_reference", "batch_id", "accepted_count", "files"].includes(key))) return false;
  return value.status === "uploaded" && typeof value.job_reference === "string" && REFERENCE.test(value.job_reference)
    && typeof value.batch_id === "string" && UUID.test(value.batch_id)
    && Number.isInteger(value.accepted_count) && Number(value.accepted_count) >= 1 && Number(value.accepted_count) <= 20
    && Array.isArray(value.files) && value.files.length === value.accepted_count
    && value.files.every(file => record(file) && Object.keys(file).every(key => ["upload_id", "file_type", "size_bytes"].includes(key))
      && typeof file.upload_id === "string" && UUID.test(file.upload_id)
      && (file.file_type === "pdf" || file.file_type === "docx") && Number.isInteger(file.size_bytes)
      && Number(file.size_bytes) > 0 && Number(file.size_bytes) <= 10 * MIB);
}

const PUBLIC_ERRORS: Record<string, string> = {
  invalid_job_reference: "Enter a valid TT-JOB reference.",
  invalid_batch: "Select between 1 and 20 PDF/DOCX files.",
  unsupported_file_type: "Only PDF/DOCX files with compatible document types are supported.",
  invalid_filename: "A selected filename is not permitted.",
  invalid_file_signature: "A selected file does not match its document type.",
  malformed_docx: "A selected DOCX package is invalid or exceeds safe limits.",
  file_too_large: "A selected file exceeds 10 MiB.",
  batch_too_large: "The batch exceeds the permitted upload size.",
  invalid_multipart: "The upload form could not be accepted. Check the file selection.",
};

export async function uploadCvs(jobReference: string, files: readonly File[]): Promise<CvUploadResponse> {
  const invalid = validateCvSelection(jobReference, files);
  if (invalid) throw new Error(invalid);
  const form = new FormData();
  form.append("job_reference", jobReference.trim());
  for (const file of files) form.append("files", file);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/cv-uploads`, {method: "POST", body: form});
  } catch {
    throw new Error("Upload was not confirmed. Check with the local demo operator before uploading again.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(record(body) && typeof body.code === "string" && Object.hasOwn(PUBLIC_ERRORS, body.code)
    ? PUBLIC_ERRORS[body.code] : "Candidate CV upload could not store the batch. No upload was confirmed.");
  if (!isCvUploadResponse(body) || body.job_reference !== jobReference.trim() || body.accepted_count !== files.length) {
    throw new Error("Upload confirmation was invalid. Check with the local demo operator before uploading again.");
  }
  return body;
}
