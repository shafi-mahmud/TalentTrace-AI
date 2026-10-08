import { createElement as h } from "react";
import type { BatchScreeningResponse } from "../types/screening";

export function ScreeningResults({result}: {result: BatchScreeningResponse}) {
  const criteria = new Map(result.snapshot.criteria.map(c => [c.criterion_id, c]));
  const labels = {eligible: "Eligible", excluded: "Excluded", insufficient_evidence: "Needs review"};
  return h("section", {className: "screening-results", "aria-label": "Candidate screening results"},
    h("h2", null, "Screening results"),
    h("p", null, `${result.snapshot.job_title} · ${result.job_reference}`),
    h("p", {className: "helper-text"}, "Session-only results. Evidence-based hard-requirement decisions; no ranking or scoring. Human review required."),
    ...result.candidates.map((candidate, index) => {
      const decision = candidate.result;
      return h("article", {key: candidate.upload_id, className: "cv-candidate-profile"},
        h("h3", null, `Upload ${index + 1}`),
        h("p", {role: "status"}, !decision ? "Processing failed — no candidate decision."
          : decision.status === "source_unavailable" ? "Source unavailable — no candidate decision."
          : decision.status === "matching_failed" ? "Matching failed — no candidate decision."
          : labels[decision.screening_decision!]),
        decision?.exclusion_reasons.length ? h("ul", null, ...decision.exclusion_reasons.map(reason =>
          h("li", {key: reason.criterion_id}, `${criteria.get(reason.criterion_id)?.description}: ${reason.message}`))) : null,
        decision?.matching_result.matches.map(match => {
          const criterion = criteria.get(match.criterion_id)!;
          return h("details", {key: match.criterion_id, className: "requirement-evidence"},
            h("summary", null, `${criterion.description} · ${criterion.is_hard ? "Mandatory" : "Preferred"} · ${match.match_status.replaceAll("_", " ")}`),
            h("p", null, `${criterion.category} · ${match.match_method}`), h("p", null, match.explanation),
            match.evidence.length ? h("ul", null, ...match.evidence.map(evidence => h("li", {key: evidence.fact_id}, evidence.value,
              h("small", {className: "helper-text"}, ` — ${evidence.source.kind === "page" ? "Page" : "Block"} ${evidence.source.number} · ${evidence.source.method === "ocr" ? "OCR" : "Digital"}`))))
              : h("p", null, "No supporting evidence identified in supplied qualifications."));
        }));
    }));
}
