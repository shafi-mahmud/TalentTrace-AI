import { createElement as h } from "react";
import type { CandidateScore, ScoringBatch } from "../types/screening";

export function ScoringProvenance({provenance}:{provenance:ScoringBatch['ai_provenance']}) {
 return h('p',{className:'helper-text'},provenance
  ? `AI processing: ${provenance.provider==='groq'?'Groq':'Local Ollama'} · ${provenance.model}. ${provenance.external_processing_confirmed?'External processing confirmed.':'Local processing.'}`
  : 'AI provider was not recorded for this saved run.');
}

const reasons = {
  processing_failed: "Processing failed; no reliable evaluation is available.",
  screening_incomplete: "Source or matching evidence is incomplete.",
  not_eligible: "The screening eligibility gate did not pass.",
  uncertain_evidence: "A weighted requirement has ambiguous evidence. Human review is needed.",
  missing_dimension_criteria: "A weighted dimension has no approved criteria. Review weights; use 0 for unused dimensions.",
};

export function ScoreDetails({score}: {score: CandidateScore}) {
  if (score.status !== "scored") return h("p", {className: "helper-text"}, `Not scored - ${reasons[score.reason!]}`);
  return h("section", {"aria-label": "Evidence-based score"},
    h("p", {className: "rank-label"}, h("strong", null, `${score.score!.toFixed(2)} / 100`), " Weighted requirement coverage"),
    h("details", {className: "evidence-disclosure"}, h("summary", null, "Score breakdown"),
      ...score.dimensions.map(d => h("div", {key: d.category}, h("strong", null, d.category),
        h("p", null, `${d.weight}% weight - ${d.supported_count}/${d.total_requirements} supported - ${d.weighted_points.toFixed(2)} points`),
        h("p", {className: "helper-text"}, "Original requirement explanations and source references remain below."))),
      h("p", {className: "helper-text"}, "Scores measure demonstrated requirements, not a hiring recommendation. Human review required.")));
}
