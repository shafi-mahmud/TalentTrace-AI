import { createElement as h } from "react";
import type { CandidateAttribute, CandidateProfilesResponse } from "../types/candidateProfile";
import type { CvExtractionResponse } from "../types/cvExtraction";

export function CandidateProfileAction({extraction, ocrAttempted, busy, parsing, onParse}: {
  extraction: CvExtractionResponse | null; ocrAttempted: boolean; busy: boolean; parsing: boolean; onParse: () => void;
}) {
  if (!extraction || (extraction.files.some(file => file.extraction_status === "ocr_required") && !ocrAttempted)) return null;
  return h("div", {className: "cv-upload-success"},
    h("button", {type: "button", className: "button button-primary", disabled: busy, onClick: onParse}, parsing ? "Extracting candidate profiles…" : "Extract candidate profiles"),
    h("p", {className: "helper-text"}, "Uses the selected CV AI provider. Synthetic/sample data only; no screening or scoring."));
}

function fact(value: CandidateAttribute | null, label: string, index = 0) {
  if (!value) return null;
  const source = value.source;
  return h("li", {key: `${label}-${index}`}, h("strong", null, `${label}: `), value.value,
    h("small", {className: "helper-text"}, ` (${source.kind === "page" ? "Page" : "Block"} ${source.number}${source.method === "ocr" ? " · OCR" : ""})`));
}

export function CandidateProfilesSummary({result}: {result: CandidateProfilesResponse}) {
  return h("section", {"aria-label": "Structured candidate profiles", className: "cv-upload-success"},
    h("h2", null, "Candidate profiles"), h("p", {className: "helper-text"}, "Source-backed extraction, not a suitability decision. Profiles are not saved."),
    ...result.candidates.map((candidate, index) => h("article", {key: candidate.upload_id, className: "cv-candidate-profile"},
      h("h3", null, `Upload ${index + 1}`),
      candidate.parsing_status !== "parsed" ? h("p", {role: "status"}, candidate.parsing_status === "source_unavailable"
        ? "Source unavailable. Extraction or OCR could not provide usable evidence; this does not mean missing qualifications."
        : "Parsing failed. A grounded profile could not be produced; this is not a rejection.")
      : h("div", null,
        h("h4", null, "Contact"), h("ul", null,
          fact(candidate.contact!.candidate_name, "Name"), fact(candidate.contact!.location, "Location"),
          ...candidate.contact!.emails.map((item, i) => fact(item, "Email", i)),
          ...candidate.contact!.phones.map((item, i) => fact(item, "Phone", i)),
          ...candidate.contact!.links.map((item, i) => fact(item, "Link", i))),
        h("h4", null, "Education"), candidate.qualifications!.education.length ? h("div", null,
          ...candidate.qualifications!.education.map((entry, i) => h("ul", {key: i}, fact(entry.institution, "Institution"),
            fact(entry.qualification, "Qualification"), fact(entry.field_of_study, "Field of study"), fact(entry.date_or_period, "Period")))) : h("p", null, "Not stated."),
        h("h4", null, "Work history"), candidate.qualifications!.work_history.length ? h("div", null,
          ...candidate.qualifications!.work_history.map((entry, i) => h("ul", {key: i}, fact(entry.employer, "Employer"),
            fact(entry.role_title, "Role"), fact(entry.date_or_period, "Period"), fact(entry.location, "Work location"),
            ...entry.responsibilities_or_achievements.map((item, j) => fact(item, "Activity", j))))) : h("p", null, "Not stated."),
        h("h4", null, "Skills"), candidate.qualifications!.skills.length ? h("ul", null,
          ...candidate.qualifications!.skills.map((item, i) => fact(item, "Skill", i))) : h("p", null, "Not stated.")))));
}
