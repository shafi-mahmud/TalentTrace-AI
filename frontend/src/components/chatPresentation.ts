import { createElement as h } from "react";
import type { ReactNode } from "react";
import { MISSING_FIELD_LABELS } from "../types/recruiterChat.ts";
import type { ChatMessage, RecruiterChatResponse, PublicationState } from "../types/recruiterChat";
import type { JobDescriptionGenerationResponse } from "../types/jobDescription";
import type { WorkingCriteriaDraft } from "../types/recruiterChat";
import SavedJobIdentity from './SavedJobIdentity.ts';

export function replyToChatMessage(reply: RecruiterChatResponse): ChatMessage {
  return { role: "assistant", text: reply.assistant_message, conversationId: reply.conversation_id,
    ...(reply.status === "clarification" ? { missingFields: reply.missing_fields } : {}),
    ...(reply.status === "jd_generated" ? { jobDescriptionResult: reply.job_description_result, publishingContext: reply.publishing_context,
      screeningSuggestions: reply.screening_suggestions, draftId: reply.draft_id,
      jobReference: reply.job_reference ?? undefined, jobRevision: reply.job_revision,
      screeningSuggestionSources: reply.screening_suggestion_sources } : {}),
  };
}

export function RecruiterChatPage({ children }: { children: ReactNode }) {
  return h("div", { className: "app-shell chat-page jd-page" },
    h("main", null,
      h("div", { className: "page-intro" },
        h("h1", null, "Job description assistant"),
        h("p", { className: "page-description" }, "Describe the role, create a draft and review it in one conversation.")),
      h("aside", { className: "chat-policy-source", "aria-label": "Company Policy Knowledge Source" },
        h("span", { className: "demo-badge" }, "Demo policy source"),
        h("span", null, "Synthetic Demo Company Policy"),
        h("details", {className:"supporting-details"},h("summary",null,"How it works"),
          h("p",null,"Server-side grounding · Semantic BGE + pgvector. Review generated content and its policy citations before publishing."))),
      children));
}

export function EmptyConversation() {
  return h("div",{className:"chat-empty"},h("h3",null,"What role are you hiring for?"),
    h("p",null,"Describe the role and required skills, or load the synthetic demo to get started."));
}

function resultList(title: string, items: string[], skills = false) {
  return h("section", { className: "result-section", "aria-label": title },
    h("h3", null, title), h("ul", { className: skills ? "skill-list" : undefined },
      ...items.map((item, index) => h("li", { key: index }, item))));
}

function DraftMessage({ result, publication = {status: "idle"}, criteriaDraft, onPublish, onRevise, onContinue, actionsDisabled }: {
  result: JobDescriptionGenerationResponse; publication?: PublicationState;
  criteriaDraft?: WorkingCriteriaDraft; onCriteriaChange?: (criteria: WorkingCriteriaDraft["criteria"]) => void;
  onCriteriaReviewed?: (reviewed: boolean) => void; onContinue?: () => void;
  onPublish?: () => void; onRevise?: () => void; actionsDisabled?: boolean;
}) {
  const draft = result.job_description;
  const sources = new Map<string, Set<string>>();
  for (const citation of result.grounding_citations) {
    const sections = sources.get(citation.source_title) ?? new Set<string>();
    for (const path of citation.heading_paths) {
      const section = path[path.length - 1];
      if (section && section !== citation.source_title) sections.add(section);
    }
    sources.set(citation.source_title, sections);
  }
  return h("div", { className: "chat-draft" },
    h("div", { className: "draft-notice" }, h("span", { className: "draft-badge" }, "Draft"),
      h("span", {className: "review-badge"}, "Human review required"), h("span", {className: "grounded-badge"}, "Policy grounded"),
      h("p", null, publication.status === "success" ? "Published as a demo. Formal approval is not recorded." : "Review this draft and its saved job identity before continuing.")),
    h("article", { className: "job-description" },
      h("h2", { className: "generated-title" }, draft.title),
      h("section", { className: "result-section" }, h("h3", null, "Summary"), h("p", null, draft.summary)),
      resultList("Responsibilities", draft.responsibilities), resultList("Required Skills", draft.required_skills, true),
      draft.preferred_skills.length ? resultList("Preferred Skills", draft.preferred_skills) : null,
      resultList("Qualifications", draft.qualifications)),
    criteriaDraft ? h("p", {className: "helper-text"}, "Screening requirements are available in Candidate Screening. Review and confirm them there.") : null,
    h("details", { className: "grounding-section", "aria-label": "Policy Grounding" }, h("summary", null, "Policy Grounding · Sources and citations"),
      h("div", { className: "grounding-header" }, h("h3", null, "Policy Grounding"), h("span", { className: "demo-badge" }, "Demo policy source")),
      h("p", { className: "grounding-description" }, "Grounded in synthetic company policy for this demo."),
      h("ul", { className: "policy-sources" }, ...Array.from(sources, ([title, sections]) =>
        h("li", { key: title }, h("h4", null, title), h("ul", { className: "policy-sections", "aria-label": "Referenced policy sections" },
          ...Array.from(sections, section => h("li", { key: section }, section)))))),
      h("details", { className: "technical-details" }, h("summary", null, "Technical details"),
        h("dl", { className: "generation-metadata" },
          ...[["Provider", result.provider === "ollama" ? "Ollama" : "Groq"], ["Model", result.model], ["Retrieval", "Semantic BGE + exact pgvector cosine"]].map(([label, value]) =>
            h("div", { key: label }, h("dt", null, label), h("dd", null, value)))),
        h("h4", null, "Citation IDs"), h("ul", { className: "technical-citations" },
          ...result.grounding_citations.map(citation => h("li", { key: citation.citation_id },
            h("span", null, citation.source_title), h("code", null, citation.citation_id)))))),
    h("footer", {className: "draft-actions"},
      h("button", {type: "button", className: "button button-primary", onClick: onPublish, disabled: !onPublish || actionsDisabled || publication.status === "loading"},
        publication.status === "loading" ? "Publishing…" : "Review publishing"),
      h("button", {type: "button", className: "button button-secondary", onClick: onRevise, disabled: !onRevise || actionsDisabled || publication.status === "loading"}, "Revise draft")),
    onContinue ? h('button',{type:'button',className:'button button-secondary',disabled:actionsDisabled,onClick:onContinue},'Review screening criteria for this job') : null,
    publication.status === "loading" ? h("p", {role: "status", className: "publication-note"}, "Publishing once through MCP…") : null,
    publication.status === "success" ? h("div", {role: "status", className: "publication-success"},
      h("strong", null, "Publication confirmed"), h("dl", null,
        ...[["Destination", publication.result.destination], ["Status", publication.result.status], ["External ID", publication.result.external_id]].map(([label, value]) =>
          h("div", {key: label}, h("dt", null, label), h("dd", null, value))))) : null,
    publication.status === "failed" ? h("p", {role: "alert", className: "error-banner"}, publication.message) : null);

}

// All recruiter/provider content renders as escaped React text, never raw HTML.
export function ChatMessageView({ message, criteriaDraft, onCriteriaChange, onCriteriaReviewed, onContinue, onPublish, onRevise, onRetry, actionsDisabled }: {
  message: ChatMessage; criteriaDraft?: WorkingCriteriaDraft;
  onCriteriaChange?: (criteria: WorkingCriteriaDraft["criteria"]) => void; onCriteriaReviewed?: (reviewed: boolean) => void;
  onContinue?: () => void; onPublish?: () => void; onRevise?: () => void; onRetry?: () => void; actionsDisabled?: boolean;
}) {
  return h("div", { className: `chat-message chat-${message.role}` },
    h("strong", null, message.role === "recruiter" ? "You" : "TalentTrace AI"),
    h("p", null, message.text),
    message.jobDescriptionResult ? h(SavedJobIdentity,{jobReference:message.jobReference,revision:message.jobRevision,internalId:message.draftId}) : null,
    message.sendState === "sending" ? h("p", {role: "status"}, "Sending…") : null,
    message.sendState === "failed" ? h("div", {role: "alert", className: "error-banner chat-send-error"},
      h("p", null, "Message was not confirmed as sent. Your text remains in the composer.", message.sendError ? ` ${message.sendError}` : ""),
      message.retryAvailable && onRetry ? h("button", {type: "button", className: "button button-secondary", disabled: actionsDisabled, onClick: onRetry}, "Retry message") : null) : null,
    message.sendState === "uncertain" ? h("div", {role: "alert", className: "error-banner chat-send-error"},
      h("p", null, "Delivery was not confirmed. The server may have accepted this request; it was not retried automatically.",
        message.sendError ? ` ${message.sendError}` : ""),
      message.retryAvailable && onRetry ? h("button", {type: "button", className: "button button-secondary", disabled: actionsDisabled, onClick: onRetry}, "Retry in this conversation") : null) : null,
    message.missingFields?.length ? h("ul", { "aria-label": "Information needed" },
      ...message.missingFields.map(field => h("li", { key: field }, MISSING_FIELD_LABELS[field]))) : null,
    message.role === "assistant" && message.jobDescriptionResult
      ? h(DraftMessage, { result: message.jobDescriptionResult, publication: message.publication, criteriaDraft,
        onCriteriaChange, onCriteriaReviewed, onContinue, onPublish, onRevise, actionsDisabled }) : null);
}
