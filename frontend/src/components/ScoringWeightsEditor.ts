import { createElement as h } from "react";
import { isScoringWeights } from "../api/scoring.ts";
import type { ScoringWeights } from "../types/screening";

export function ScoringWeightsEditor({weights, disabled, reviewed, onChange}: {
  weights: ScoringWeights; disabled: boolean; reviewed: boolean; onChange: (weights: ScoringWeights) => void;
}) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  return h("fieldset", {disabled, className: "card"}, h("legend", null, "Scoring weights (%)"),
    h("p", {className: "helper-text"}, "Provisional 50/30/20. Confirm weights with requirements. Use 0 for unused dimensions; missing or ambiguous weighted evidence is not scored."),
    ...(["skill", "experience", "education"] as const).map(category => h("div", {className: "field", key: category},
      h("label", {htmlFor: `weight-${category}`}, category[0].toUpperCase() + category.slice(1)),
      h("input", {id: `weight-${category}`, type: "number", min: 0, max: 100, step: 1,
        value: Number.isFinite(weights[category]) ? weights[category] : "",
        onChange: (event: {target: {value: string}}) => onChange({...weights, [category]: event.target.value === "" ? NaN : Number(event.target.value)})}))),
    h("p", {role: "status"}, `Total: ${Number.isFinite(total) ? total : "Incomplete"}%${isScoringWeights(weights) ? "" : " - must total 100"}`),
    !reviewed && h("p", {className: "helper-text"}, "Criteria and weights need confirmation before screening."));
}
