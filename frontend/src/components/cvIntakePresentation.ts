import { createElement as h } from "react";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";

export type WorkspaceMode = "jd" | "cv";

export function WorkspaceNavigation({mode, onChange}: {mode: WorkspaceMode; onChange: (mode: WorkspaceMode) => void}) {
  return h("nav", {className: "workspace-modes", "aria-label": "Recruiter workspace views"},
    h("button", {type: "button", "aria-pressed": mode === "jd", onClick: () => onChange("jd")}, "JD Assistant"),
    h("button", {type: "button", "aria-pressed": mode === "cv", onClick: () => onChange("cv")}, "CV Intake"));
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
    h("p", {className: "helper-text"}, "Files stored privately. Candidate parsing and screening are not implemented yet."),
    onExtract && h("button", {type: "button", className: "button button-primary", disabled: extracting, onClick: onExtract}, extracting ? "Extracting text…" : "Extract text"));
}

export function CvExtractionSummary({result}: {result: CvExtractionResponse}) {
  return h("section", {className: "cv-upload-success", "aria-label": "CV extraction status", role: "status"},
    h("h2", null, `${result.processed_count} CV${result.processed_count === 1 ? "" : "s"} processed`),
    h("ul", {className: "cv-extraction-list"}, ...result.files.map((file, index) => h("li", {key: file.upload_id},
      h("strong", null, `File ${index + 1} · ${file.file_type.toUpperCase()} · `),
      file.extraction_status === "text_extracted"
        ? `Text extracted · ${file.source_unit_count} ${file.file_type === "pdf" ? (file.source_unit_count === 1 ? "page" : "pages") : (file.source_unit_count === 1 ? "block" : "blocks")}`
        : file.extraction_status === "ocr_required" ? "OCR required" : "Extraction failed",
      file.extraction_status === "ocr_required" && h("p", {className: "helper-text"}, "Digital text was insufficient. OCR processing is not implemented yet."),
      file.extraction_status === "extraction_failed" && h("p", {className: "helper-text"}, "Text could not be extracted. This is not evidence of missing qualifications.")))));
}
