import { createElement as h } from "react";
import type {ReactNode} from "react";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";
import type { CvOcrResponse } from "../types/cvOcr";
import type { WorkingCriteriaDraft } from "../types/recruiterChat";
import { isValidJobReference } from "../api/cvUploads.ts";
import type { ScreeningCriterion } from "../types/screening";
import type { BatchScreeningResponse, ReviewedJobSnapshot } from "../types/screening";

type ResettableCriteriaContext = {
  reference: string; manualDraft: WorkingCriteriaDraft | null; manualJobTitle: string; setupError: string;
  snapshot: ReviewedJobSnapshot | null; screening: BatchScreeningResponse | null;
};

export function resetCriteriaContextForNewChat<T extends ResettableCriteriaContext>(state: T): T {
  return {...state, reference: "", manualDraft: null, manualJobTitle: "", setupError: "", snapshot: null, screening: null};
}

export type WorkspaceMode = "home" | "jd" | "cv" | "scheduling";

export function screeningPrerequisiteMessage({busy, hasSuggestions, hasBatch, hasSnapshot, referenceMatches}: {
  busy: boolean; hasSuggestions: boolean; hasBatch: boolean; hasSnapshot: boolean; referenceMatches: boolean;
}): string | null {
  if (busy) return "Wait for the current operation to finish.";
  if (!hasSuggestions) return "Set up a job title and screening criteria first. A JD is optional.";
  if (!hasSnapshot) return "Review and explicitly confirm screening criteria for this job.";
  if (!hasBatch) return "Upload a CV batch for this Job Reference first.";
  if (!referenceMatches) return "The confirmed Job Reference must match the uploaded batch.";
  return null;
}

export function WorkspaceNavigation({mode, onChange, accountControls}: {mode: WorkspaceMode; onChange: (mode: WorkspaceMode) => void; accountControls?:ReactNode}) {
  return h("header", {className: "app-topbar"},
    h("div", {className: "app-topbar-inner"},
      h("a", {className: "brand", href: "/", "aria-label": "TalentTrace AI home"},
        h("span", {className: "brand-mark", "aria-hidden": true}, "T"),
        h("span", null, "TalentTrace", h("span", {className: "brand-ai"}, " AI"))),
      h("nav", {className: "workspace-modes", "aria-label": "Recruiter workspace views"},
        h("button", {type: "button", "aria-pressed": mode === "home", onClick: () => onChange("home")}, "Home"),
        h("button", {type: "button", "aria-pressed": mode === "jd", onClick: () => onChange("jd")}, "JD Assistant"),
        h("button", {type: "button", "aria-pressed": mode === "cv", onClick: () => onChange("cv")}, "Candidate Screening"),
        h("button", {type: "button", "aria-pressed": mode === "scheduling", onClick: () => onChange("scheduling")}, "Interview Scheduling")),
      h("div",{className:"header-account"},accountControls)));
}

export function ScreeningWorkflowSteps({hasSuggestions, hasSnapshot, hasBatch, isScreened}: {
  hasSuggestions: boolean; hasSnapshot: boolean; hasBatch: boolean; isScreened: boolean;
}) {
  const steps = [
    {label: hasSuggestions ? "Review job criteria" : "Set up job criteria", complete: hasSnapshot, available: true},
    {label: "Upload or select imported CVs", complete: hasBatch, available: true},
    {label: "Prepare documents · OCR when needed", complete: isScreened, available: hasBatch},
    {label: "Run AI screening", complete: isScreened, available: hasBatch && hasSnapshot},
    {label: "Review ranked applicants and evidence", complete: false, available: isScreened},
    {label: "Select an eligible candidate to schedule", complete: false, available: isScreened},
  ];
  return h("ol", {className: "workflow-steps", "aria-label": "Screening workflow progress"},
    ...steps.map((step, index) => h("li", {key: step.label, className: step.complete ? "is-complete" : step.available ? "is-current" : "is-upcoming"},
      h("span", {className: "workflow-step-number", "aria-hidden": true}, step.complete ? "✓" : String(index + 1)),
      h("span", null, step.label),
      h("span", {className: "sr-only"}, step.complete ? " complete" : step.available ? " available" : " not yet available"))));
}

export function createManualCriteriaDraft(jobTitle: string, jobReference: string): WorkingCriteriaDraft | null {
  const title = jobTitle.trim();
  if (!title || title.length > 120 || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(title) || !isValidJobReference(jobReference)) return null;
  const criteria: ScreeningCriterion[] = [];
  return {draftId: `manual-${crypto.randomUUID()}`, origin: "manual", suggestions: {job_title: title, criteria},
    sources: [], criteria, reviewed: false};
}

export function SelectedCvFiles({files, onRemove, disabled}: {
  files: readonly Pick<File, "name" | "size">[]; onRemove: (index: number) => void; disabled: boolean;
}) {
  return h("ul", {className: "cv-selected-files", "aria-label": "Selected CV files"},
    ...files.map((file, index) => h("li", {key: index},
      h("div", null, h("span", {className: "cv-local-name"}, file.name),
        h("small", null, `${(file.size / 1024).toFixed(1)} KiB`)),
      h("button", {type: "button", className: "button button-secondary", disabled,
        onClick: () => onRemove(index), "aria-label": `Remove selected file ${index + 1}`}, "Remove"))));
}

export function CvUploadConfirmation({result, onExtract, extracting = false}: {
  result: CvUploadResponse; onExtract?: () => void; extracting?: boolean;
}) {
  return h("section", {className: "cv-upload-success", role: "status"},
    h("h2", null, "Upload complete"), h("p", null, `${result.accepted_count} file${result.accepted_count === 1 ? "" : "s"} stored for ${result.job_reference}.`),
    h("p", null, "Batch reference"), h("code", null, result.batch_id),
    h("p", {className: "helper-text"}, "Files stored privately. Extract source-backed profiles after processing; no screening or scoring."),
    onExtract && h("button", {type: "button", className: "button button-primary", disabled: extracting, onClick: onExtract}, extracting ? "Extracting text…" : "Extract text"));
}

export function CvExtractionSummary({result, onOcr, processingOcr = false, disabled = false}: {
  result: CvExtractionResponse; onOcr?: () => void; processingOcr?: boolean; disabled?: boolean;
}) {
  return h("section", {className: "cv-upload-success", "aria-label": "CV extraction status", role: "status"},
    h("h2", null, `${result.processed_count} CV${result.processed_count === 1 ? "" : "s"} processed`),
    h("ul", {className: "cv-extraction-list"}, ...result.files.map((file, index) => h("li", {key: file.upload_id},
      h("strong", null, `File ${index + 1} · ${file.file_type.toUpperCase()} · `),
      file.extraction_status === "text_extracted"
        ? `Text extracted · ${file.source_unit_count} ${file.file_type === "pdf" ? (file.source_unit_count === 1 ? "page" : "pages") : (file.source_unit_count === 1 ? "block" : "blocks")}`
        : file.extraction_status === "ocr_required" ? "OCR required" : "Extraction failed",
      file.extraction_status === "ocr_required" && h("p", {className: "helper-text"}, "Digital text was insufficient. Run OCR to try reading this PDF."),
      file.extraction_status === "extraction_failed" && h("p", {className: "helper-text"}, "Text could not be extracted. This is not evidence of missing qualifications.")))),
    onOcr && result.files.some(file => file.extraction_status === "ocr_required") && h("button", {
      type: "button", className: "button button-primary", disabled: disabled || processingOcr, onClick: onOcr,
    }, processingOcr ? "Running OCR…" : "Run OCR"));
}

export function CvOcrSummary({result}: {result: CvOcrResponse}) {
  return h("section", {className: "cv-upload-success", role: "status", "aria-label": "CV OCR status"},
    h("h2", null, "OCR results"),
    result.attempted_count === 0 ? h("p", null, "No PDFs required OCR.") : h("ul", {className: "cv-extraction-list"},
      ...result.files.map((file, index) => h("li", {key: file.upload_id},
        h("strong", null, `OCR file ${index + 1} · PDF · `),
        file.ocr_status === "ocr_extracted" ? `OCR extracted · ${file.page_count} ${file.page_count === 1 ? "page" : "pages"}` : "OCR failed",
        file.ocr_status === "ocr_failed" && h("p", {className: "helper-text"}, "Usable text could not be recovered. This is not evidence of missing qualifications.")))),
    h("p", {className: "helper-text"}, "Extraction evidence only. Profile extraction is a separate action; no screening or scoring."));
}
