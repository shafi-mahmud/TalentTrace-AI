import { createElement as h, useState } from "react";
import { isReviewedSnapshot } from "../api/screening.ts";
import type { ReviewedJobSnapshot, ScreeningCriterion, ScreeningSuggestions } from "../types/screening";

export function confirmReviewedCriteria(suggestions: ScreeningSuggestions, jobReference: string,
  criteria: ScreeningCriterion[], acknowledged: boolean): ReviewedJobSnapshot | null {
  const snapshot = {job_title: suggestions.job_title, job_reference: jobReference,
    criteria_confirmed: true as const, criteria: criteria.map(c => ({...c}))};
  return acknowledged === true && isReviewedSnapshot(snapshot) ? snapshot : null;
}

export default function ScreeningCriteriaReview({suggestions, jobReference, disabled, onConfirm, onInvalidate}: {
  suggestions: ScreeningSuggestions; jobReference: string; disabled: boolean;
  onConfirm: (snapshot: ReviewedJobSnapshot) => void; onInvalidate: () => void;
}) {
  const [criteria, setCriteria] = useState(suggestions.criteria.map(c => ({...c})));
  const [acknowledged, setAcknowledged] = useState(false);
  function edit(next: ScreeningCriterion[]) { setCriteria(next); setAcknowledged(false); onInvalidate(); }
  function change(index: number, patch: Partial<ScreeningCriterion>) {
    edit(criteria.map((c, i) => i === index ? {...c, ...patch} : c));
  }
  const confirmed = confirmReviewedCriteria(suggestions, jobReference, criteria, acknowledged);
  return h("section", {className: "card criteria-review", "aria-label": "Review screening criteria"},
    h("h2", null, "Review screening criteria"),
    h("p", null, h("strong", null, suggestions.job_title), " · Session-only snapshot"),
    h("p", {className: "helper-text"}, "Suggestions come from your recruiter requirements, not new LLM-generated qualifications. All start as preferred. Review each description, category and mandatory flag. Confirm for the Job Reference above."),
    h("fieldset", {disabled}, h("legend", {className: "sr-only"}, "Screening requirements"),
      ...criteria.map((criterion, index) => h("div", {className: "criterion-row", key: criterion.criterion_id},
        h("label", null, `Requirement ${index + 1}`, h("input", {value: criterion.description, maxLength: 500,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => change(index, {description: e.target.value})})),
        h("label", null, "Category", h("select", {value: criterion.category,
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) => change(index, {category: e.target.value as ScreeningCriterion["category"]})},
          h("option", {value: "skill"}, "Skill"), h("option", {value: "experience"}, "Experience"), h("option", {value: "education"}, "Education"))),
        h("label", null, "Requirement type", h("select", {value: criterion.is_hard ? "mandatory" : "preferred",
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) => change(index, {is_hard: e.target.value === "mandatory"})},
          h("option", {value: "preferred"}, "Preferred"), h("option", {value: "mandatory"}, "Mandatory"))),
        h("button", {className: "button button-secondary", type: "button", onClick: () => edit(criteria.filter((_, i) => i !== index))}, `Remove requirement ${index + 1}`))),
      h("button", {className: "button button-secondary", type: "button", disabled: criteria.length >= 50,
        onClick: () => edit([...criteria, {criterion_id: `manual-${crypto.randomUUID()}`, description: "", category: "skill", is_hard: false}])}, "Add requirement"),
      h("p", {className: "helper-text"}, "Confirm 1–50 requirements. A mandatory requirement not demonstrated in parsed evidence causes exclusion; ambiguity requires review."),
      h("label", {className: "review-confirmation"}, h("input", {type: "checkbox", checked: acknowledged,
        onChange: (e: React.ChangeEvent<HTMLInputElement>) => {setAcknowledged(e.target.checked); onInvalidate();}}),
        " I reviewed these criteria and explicitly confirm the mandatory/preferred flags for this job."),
      h("button", {type: "button", className: "button button-primary", disabled: !confirmed,
        onClick: () => {if (confirmed) onConfirm(confirmed);}}, "Confirm criteria for this job")));
}
