import { createElement as h } from "react";
import { isReviewedSnapshot } from "../api/screening.ts";
import type { ReviewedJobSnapshot, ScreeningCriterion, ScreeningSuggestions } from "../types/screening";
import type { ScreeningSuggestionSource } from "../types/recruiterChat";

export function confirmReviewedCriteria(suggestions: ScreeningSuggestions, jobReference: string,
  criteria: ScreeningCriterion[], acknowledged: boolean): ReviewedJobSnapshot | null {
  const snapshot = {job_title: suggestions.job_title, job_reference: jobReference,
    criteria_confirmed: true as const, criteria: criteria.map(c => ({...c}))};
  return acknowledged === true && isReviewedSnapshot(snapshot) ? snapshot : null;
}

export function CriteriaEditor({criteria, sources, reviewed, disabled, onChange, onReviewedChange, origin = "job_description"}: {
  criteria: ScreeningCriterion[]; sources: ScreeningSuggestionSource[]; reviewed: boolean; disabled: boolean;
  origin?: "job_description" | "manual";
  onChange: (criteria: ScreeningCriterion[]) => void; onReviewedChange: (reviewed: boolean) => void;
}) {
  function edit(next: ScreeningCriterion[]) { onChange(next); onReviewedChange(false); }
  function change(index: number, patch: Partial<ScreeningCriterion>) {
    edit(criteria.map((c, i) => i === index ? {...c, ...patch} : c));
  }
  const byCriterion = new Map(sources.map(source => [source.criterion_id, source]));
  return h("section", {className: "criteria-review", "aria-label": origin === "manual" ? "Recruiter-entered screening criteria" : "Suggested screening criteria"},
    h("h3", null, origin === "manual" ? "Recruiter-entered criteria" : "Suggested screening criteria"),
    h("p", {className: "helper-text"}, origin === "manual"
      ? "Enter the job requirements to evaluate. These are recruiter-provided and are not policy-backed. They are not approved until reviewed."
      : "Suggestions come from recruiter-provided requirements. They are not approved until reviewed; an excerpt records origin, not semantic proof after edits."),
    h("fieldset", {disabled}, h("legend", {className: "sr-only"}, "Editable screening criteria"),
      ...criteria.map((criterion, index) => h("div", {className: "criterion-row", key: criterion.criterion_id},
        h("label", null, `Requirement ${index + 1}`, h("input", {value: criterion.description, maxLength: 500,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => change(index, {description: e.target.value})})),
        h("label", null, "Category", h("select", {value: criterion.category,
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) => change(index, {category: e.target.value as ScreeningCriterion["category"]})},
          h("option", {value: "skill"}, "Skill"), h("option", {value: "experience"}, "Experience"), h("option", {value: "education"}, "Education"))),
        h("label", null, "Requirement type", h("select", {value: criterion.is_hard ? "mandatory" : "preferred",
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) => change(index, {is_hard: e.target.value === "mandatory"})},
          h("option", {value: "preferred"}, "Preferred"), h("option", {value: "mandatory"}, "Mandatory"))),
        byCriterion.get(criterion.criterion_id) ? h("p", {className: "criterion-provenance"},
          h("strong", null, "Original recruiter excerpt: "), byCriterion.get(criterion.criterion_id)!.evidence) :
          h("p", {className: "criterion-provenance"}, origin === "manual" ? "Recruiter-entered; no source excerpt recorded." : "Recruiter-added; no source excerpt recorded."),
        h("button", {className: "button button-secondary", type: "button", onClick: () => edit(criteria.filter((_, i) => i !== index))}, `Remove requirement ${index + 1}`))),
      h("button", {className: "button button-secondary", type: "button", disabled: disabled || criteria.length >= 50,
        onClick: () => edit([...criteria, {criterion_id: `manual-${crypto.randomUUID()}`, description: "", category: "skill", is_hard: false}])}, "Add requirement")),
    h("label", {className: "review-confirmation"}, h("input", {type: "checkbox", checked: reviewed, disabled,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => onReviewedChange(e.target.checked)}),
      " I reviewed the descriptions and explicitly confirmed the mandatory/preferred flags."));
}

export default function ScreeningCriteriaReview({suggestions, criteria, sources, reviewed, jobReference, disabled, onChange, onReviewedChange, onConfirm, origin = "job_description"}: {
  suggestions: ScreeningSuggestions; criteria: ScreeningCriterion[]; sources: ScreeningSuggestionSource[]; reviewed: boolean;
  origin?: "job_description" | "manual";
  jobReference: string; disabled: boolean; onChange: (criteria: ScreeningCriterion[]) => void;
  onReviewedChange: (reviewed: boolean) => void; onConfirm: (snapshot: ReviewedJobSnapshot) => void;
}) {
  const confirmed = confirmReviewedCriteria(suggestions, jobReference, criteria, reviewed);
  return h("section", {className: "card criteria-review-card", "aria-label": "Review screening criteria"},
    h("h2", null, "Review screening criteria"),
    h("p", null, h("strong", null, suggestions.job_title), " · Session-only snapshot"),
    h("p", {className: "helper-text"}, "Review each description, category and mandatory flag. Confirm for the Job Reference above. Screening suggestions do not approve a candidate decision."),
    h(CriteriaEditor, {criteria, sources, reviewed, disabled, onChange, onReviewedChange, origin}),
    h("p", {className: "helper-text"}, "A mandatory requirement not demonstrated in parsed evidence causes exclusion; ambiguity requires review."),
    h("button", {type: "button", className: "button button-primary", disabled: !confirmed || disabled,
      onClick: () => {if (confirmed) onConfirm(confirmed);}}, "Confirm criteria for this job"));
}
