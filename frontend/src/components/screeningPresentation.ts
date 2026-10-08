import { createElement as h } from "react";
import type { BatchScreeningResponse, CandidateRankingEntry } from "../types/screening";

export function ScreeningResults({result}: {result: BatchScreeningResponse}) {
  const criteria = new Map(result.snapshot.criteria.map(c => [c.criterion_id, c]));
  const labels = {eligible: "Eligible", excluded: "Excluded", insufficient_evidence: "Needs review"};
  const coverageLabels = {met: "Met", partially_met: "Partially met", unmet: "Unmet — not demonstrated in the CV",
    uncertain: "Uncertain", not_evaluated: "Not evaluated"};
  return h("section", {className: "screening-results", "aria-label": "Candidate screening results"},
    h("h2", null, "Screening results"),
    h("p", null, `${result.snapshot.job_title} · ${result.job_reference}`),
    h("p", {className: "helper-text"}, "Session-only ranking within this job, batch and confirmed criteria. Supported requirements count equally; no suitability score. Human review required."),
    h("p", {className: "helper-text"}, "Ties share a rank; upload ID only controls display order. Ambiguous means uncertain evidence, not partially met."),
    renderGroups());

  function card(candidate: BatchScreeningResponse["candidates"][number], ranking?: CandidateRankingEntry) {
      const index = result.candidates.findIndex(c => c.upload_id === candidate.upload_id);
      const decision = candidate.result;
      return h("article", {key: candidate.upload_id, className: "cv-candidate-profile"},
        h("h3", null, `Upload ${index + 1}`),
        h("p", null, `Overall requirement coverage: ${coverageLabels[candidate.overall_coverage]}`),
        decision?.status === "decision_complete" ? h("p", {className: "helper-text"},
          `${decision.matching_result.matches.filter(m => m.match_status === "supported").length} of ${result.snapshot.criteria.length} requirements supported. Overall coverage is separate from the screening decision.`) : null,
        ranking ? h("p", {className: "helper-text"}, `Rank ${ranking.rank}${ranking.tied ? " · Tied" : ""} · ${ranking.supported_count} of ${ranking.total_requirements} requirements supported · ${ranking.ambiguous_count} ambiguous · ${ranking.not_found_count} not found`) : null,
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
  }
  function renderGroups() {
    const byId = new Map(result.candidates.map(c => [c.upload_id, c]));
    const groups = [
      {title: "Eligible candidate ranking", cards: result.ranking.map(entry => card(byId.get(entry.upload_id)!, entry))},
      {title: "Excluded candidates", cards: result.candidates.filter(c => c.result?.screening_decision === "excluded").map(c => card(c))},
      {title: "Needs review — insufficient evidence", cards: result.candidates.filter(c => c.result?.screening_decision === "insufficient_evidence").map(c => card(c))},
      {title: "Source unavailable", cards: result.candidates.filter(c => c.result?.status === "source_unavailable").map(c => card(c))},
      {title: "Processing failures", cards: result.candidates.filter(c => !c.result || c.result.status === "matching_failed").map(c => card(c))},
    ];
    return groups.filter((group, i) => i === 0 || group.cards.length).map(group => h("section", {key: group.title, "aria-label": group.title},
      h("h3", null, group.title), ...group.cards,
      !group.cards.length ? h("p", null, "No eligible candidates to rank.") : null));
  }
}
