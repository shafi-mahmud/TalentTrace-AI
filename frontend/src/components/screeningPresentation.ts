import { createElement as h } from "react";
import { ScoreDetails } from "./scorePresentation.ts";
import type { BatchScreeningResponse, CandidateRankingEntry } from "../types/screening";

export function ScreeningResults({result, onSelectCandidate}: {result: BatchScreeningResponse; onSelectCandidate?: (uploadId:string)=>void}) {
  const criteria = new Map(result.snapshot.criteria.map(c => [c.criterion_id, c]));
  const labels = {eligible: "Eligible", excluded: "Excluded", insufficient_evidence: "Needs review"};
  const coverageLabels = {met: "Met", partially_met: "Partially met", unmet: "Unmet — not demonstrated in the CV",
    uncertain: "Uncertain", not_evaluated: "Not evaluated"};
  const excludedCount = result.candidates.filter(candidate => candidate.result?.screening_decision === "excluded").length;
  const reviewCount = result.candidates.filter(candidate => candidate.result?.screening_decision === "insufficient_evidence").length;
  const notEvaluatedCount = result.candidates.filter(candidate => candidate.overall_coverage === "not_evaluated").length;
  return h("section", {className: "screening-results", "aria-label": "Candidate screening results"},
    h("div", {className: "results-heading"}, h("div", null, h("p", {className: "eyebrow"}, "Batch complete"),
      h("h2", null, "Screening results"), h("p", {className: "results-job-title"}, `${result.snapshot.job_title} · ${result.job_reference}`)),
      h("span", {className: "results-session-badge"}, result.scoring ? "Saved scores" : "Session results")),
    h("p", {className: "helper-text"}, result.scoring ? "Saved evidence-based scores for this approved job revision. Only eligible scored candidates are ranked; ties share a rank. Human review required." : "Session-only ranking within this job, batch and confirmed criteria. Supported requirements count equally; no suitability score. Human review required."),
    h("p", {className: "helper-text"}, "Ties share a rank; upload ID only controls display order. Ambiguous means uncertain evidence, not partially met."),
    h("div", {className: "results-summary", "aria-label": "Candidate outcome summary"},
      summaryCard("Candidates processed", result.processed_count, "All batch files"),
      summaryCard("Eligible", result.ranking.length, result.scoring ? "Complete scores ranked by weighted coverage" : "Ranked by supported requirements"),
      summaryCard("Excluded", excludedCount, "Mandatory requirement not demonstrated"),
      summaryCard("Needs review", reviewCount, "Uncertain evidence"),
      summaryCard("Not evaluated", notEvaluatedCount, "Source or processing issue")),
    renderGroups());

  function summaryCard(label: string, count: number, description: string) {
    return h("article", {key: label, className: "results-summary-card"},
      h("span", null, label), h("strong", null, count), h("small", null, description));
  }

  function card(candidate: BatchScreeningResponse["candidates"][number], ranking?: Pick<CandidateRankingEntry, "rank" | "tied">) {
      const index = result.candidates.findIndex(c => c.upload_id === candidate.upload_id);
      const decision = candidate.result;
      const supported = decision?.status === "decision_complete" ? decision.matching_result.matches.filter(m => m.match_status === "supported").length : 0;
      const ambiguous = decision?.status === "decision_complete" ? decision.matching_result.matches.filter(m => m.match_status === "ambiguous").length : 0;
      const notFound = decision?.status === "decision_complete" ? decision.matching_result.matches.filter(m => m.match_status === "not_found").length : 0;
      const outcome = !decision ? "Processing failed — no candidate decision."
        : decision.status === "source_unavailable" ? "Source unavailable — no candidate decision."
        : decision.status === "matching_failed" ? "Matching failed — no candidate decision."
        : labels[decision.screening_decision!];
      return h("article", {key: candidate.upload_id, className: "cv-candidate-profile candidate-result-card"},
        h("div", {className: "candidate-card-heading"}, h("h4", null, `Candidate ${String(index + 1).padStart(2, "0")} · Upload ${index + 1}`),
          h("span", {className: `outcome-badge outcome-${decision?.screening_decision ?? decision?.status ?? "failed"}`}, outcome)),
        h("div", {className: "candidate-facts"},
          h("p", {className: "coverage-label"}, `Overall requirement coverage: ${coverageLabels[candidate.overall_coverage]}`),
          ranking ? h("p", {className: "rank-label"}, h("strong", null, `Rank ${ranking.rank}${ranking.tied ? " · Tied" : ""}`),
            h("span", null, `${supported} of ${result.snapshot.criteria.length} supported`)) : null),
        result.scoring ? h(ScoreDetails, {score: result.scoring.candidates.find(c => c.upload_id === candidate.upload_id)!}) : null,
        result.scoring && decision?.status === "decision_complete" && decision.screening_decision === "eligible" && onSelectCandidate
          ? h("button", {type:"button",className:"button button-secondary",onClick:()=>onSelectCandidate(candidate.upload_id)},"Select for interview") : null,
        decision?.status === "decision_complete" ? h("p", {className: "helper-text"},
          `${supported} of ${result.snapshot.criteria.length} requirements supported · ${ambiguous} ambiguous · ${notFound} not found. Overall coverage is separate from the screening decision.`) : null,
        decision?.exclusion_reasons.length ? h("ul", null, ...decision.exclusion_reasons.map(reason =>
          h("li", {key: reason.criterion_id}, `${criteria.get(reason.criterion_id)?.description}: ${reason.message}`))) : null,
        decision?.status === "decision_complete" ? h("details", {className: "evidence-disclosure"}, h("summary", null, "Review requirement evidence"),
          ...decision.matching_result.matches.map(match => {
          const criterion = criteria.get(match.criterion_id)!;
          return h("details", {key: match.criterion_id, className: "requirement-evidence"},
            h("summary", null, `${criterion.description} · ${criterion.is_hard ? "Mandatory" : "Preferred"} · ${match.match_status.replaceAll("_", " ")}`),
            h("p", null, `${criterion.category} · ${match.match_method}`), h("p", null, match.explanation),
            match.evidence.length ? h("ul", null, ...match.evidence.map(evidence => h("li", {key: evidence.fact_id}, evidence.value,
              h("small", {className: "helper-text"}, ` — ${evidence.source.kind === "page" ? "Page" : "Block"} ${evidence.source.number} · ${evidence.source.method === "ocr" ? "OCR" : "Digital"}`))))
              : h("p", null, "No supporting evidence identified in supplied qualifications."));
        })) : null);
  }
  function renderGroups() {
    const byId = new Map(result.candidates.map(c => [c.upload_id, c]));
    const groups = [
      {title: "Eligible candidate ranking", cards: (result.scoring?.ranking ?? result.ranking).map(entry => card(byId.get(entry.upload_id)!, entry))},
      {title: "Eligible - Not scored", cards: result.scoring ? result.scoring.candidates.filter(c => c.screening_decision === "eligible" && c.status !== "scored").map(c => card(byId.get(c.upload_id)!)) : []},
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
