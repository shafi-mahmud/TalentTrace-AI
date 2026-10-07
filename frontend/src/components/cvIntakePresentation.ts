import { createElement as h } from "react";
import type { CvUploadResponse } from "../types/cvUpload";

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

export function CvUploadConfirmation({result}: {result: CvUploadResponse}) {
  return h("section", {className: "cv-upload-success", role: "status"},
    h("h2", null, "Upload complete"), h("p", null, `${result.accepted_count} file${result.accepted_count === 1 ? "" : "s"} stored for ${result.job_reference}.`),
    h("p", null, "Batch reference"), h("code", null, result.batch_id),
    h("p", {className: "helper-text"}, "Files stored only. CV parsing and screening are not implemented yet."));
}
