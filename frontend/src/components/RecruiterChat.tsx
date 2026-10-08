import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { isValidRecruiterMessage, sendRecruiterMessage } from "../api/recruiterChat";
import { publishDraft } from "../api/jobPublishing";
import type { ChatMessage, WorkingCriteriaDraft } from "../types/recruiterChat";
import { ChatMessageView, replyToChatMessage } from "./chatPresentation";

const DEMO_INSTRUCTION = "Create a Backend AI Engineer JD for a team building FastAPI services. Responsibilities include building APIs and automated tests. Required skills are Python, FastAPI and PostgreSQL. No minimum experience required.";

export default function RecruiterChat({drafts, onDraftGenerated, onCriteriaChange, onCriteriaReviewed, onContinueToCv}: {
  drafts: Record<string, WorkingCriteriaDraft>;
  onDraftGenerated: (draft: WorkingCriteriaDraft) => void;
  onCriteriaChange: (draftId: string, criteria: WorkingCriteriaDraft["criteria"]) => void;
  onCriteriaReviewed: (draftId: string, reviewed: boolean) => void;
  onContinueToCv: (draftId: string) => void;
}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [publishingBusy, setPublishingBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const pending = useRef(false);
  const history = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const publishing = useRef(new Set<number>());

  async function publish(index: number) {
    const message = messages[index];
    if (!message?.jobDescriptionResult || publishing.current.has(index) || (message.publication && message.publication.status !== "idle")) return;
    if (!window.confirm("Publish this reviewed synthetic demo draft to Discord? This sends a real message. Use demo data only.")) return;
    publishing.current.add(index);
    setPublishingBusy(true);
    setMessages(previous => previous.map((item, i) => i === index ? {...item, publication: {status: "loading"}} : item));
    try {
      const result = await publishDraft(message.jobDescriptionResult, message.publishingContext);
      setMessages(previous => previous.map((item, i) => i === index ? {...item, publication: {status: "success", result}} : item));
    } catch (failure) {
      const text = failure instanceof Error ? failure.message : "Publication was not confirmed. Check Discord before another attempt.";
      setMessages(previous => previous.map((item, i) => i === index ? {...item, publication: {status: "failed", message: text}} : item));
    } finally {
      publishing.current.delete(index);
      setPublishingBusy(publishing.current.size > 0);
    }
  }

  function revise(message: ChatMessage) {
    if (sending) return;
    setInput(message.sourceInstruction ?? "");
    setError("");
    composer.current?.focus();
  }
  useEffect(() => {
    const container = history.current;
    if (!container) return;
    if (messages.at(-1)?.jobDescriptionResult) {
      const cards = container.querySelectorAll<HTMLElement>(".chat-message");
      const latest = cards[cards.length - 1];
      if (latest) container.scrollTop += latest.getBoundingClientRect().top - container.getBoundingClientRect().top - 16;
    } else container.scrollTop = container.scrollHeight;
  }, [messages, sending]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const message = input.trim();
    if (!isValidRecruiterMessage(message)) {
      setError("Enter job instructions of up to 4000 characters without unsafe control characters.");
      return;
    }
    pending.current = true;
    setSending(true);
    setError("");
    setMessages(previous => [...previous, {role: "recruiter", text: message}]);
    try {
      const reply = await sendRecruiterMessage(message, conversationId);
      setConversationId(reply.conversation_id);
      setMessages(previous => [...previous, {...replyToChatMessage(reply), sourceInstruction: message}]);
      setInput("");
      if (reply.status === "jd_generated") onDraftGenerated({draftId: reply.draft_id,
        origin: "job_description",
        suggestions: reply.screening_suggestions, sources: reply.screening_suggestion_sources,
        criteria: reply.screening_suggestions.criteria.map(c => ({...c})), reviewed: false});
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Recruiter chat could not be completed.");
    } finally {
      pending.current = false;
      setSending(false);
    }
  }

  return <section className="card chat-card" aria-labelledby="chat-title">
    <div className="card-header">
      <div><h2 id="chat-title">Recruiter chatbot</h2><p>Share requirements over a few messages. I’ll ask about anything missing.</p></div>
      <div className="chat-header-actions">
        <button type="button" className="button button-secondary" disabled={sending} onClick={() => {setInput(DEMO_INSTRUCTION); setError("");}}>Load demo</button>
          <button type="button" className="button button-secondary" disabled={sending || publishingBusy} onClick={() => {setMessages([]); setConversationId(undefined); setInput(""); setError("");}}>New chat</button>
      </div>
    </div>
    <div ref={history} className="chat-history" role="log" aria-label="Recruiter conversation" aria-live="polite">
      {messages.length ? messages.map((message, index) => {
        const draft = message.draftId ? drafts[message.draftId] : undefined;
        return <ChatMessageView key={index} message={message} criteriaDraft={draft}
          onCriteriaChange={draft ? criteria => onCriteriaChange(draft.draftId, criteria) : undefined}
          onCriteriaReviewed={draft ? reviewed => onCriteriaReviewed(draft.draftId, reviewed) : undefined}
          onContinue={draft ? () => onContinueToCv(draft.draftId) : undefined}
          onPublish={() => void publish(index)} onRevise={() => revise(message)} actionsDisabled={sending} />;
      }) : <p className="helper-text">Start with a job title and purpose. I’ll gather responsibilities, skills and the experience requirement before drafting.</p>}
      {sending && <p role="status">Checking the requirements you shared…</p>}
    </div>
    <form className="chat-composer" onSubmit={submit}>
      <div className="field">
        <label htmlFor="chat-message">Your job instruction</label>
        <textarea ref={composer} id="chat-message" rows={3} maxLength={4000} value={input} disabled={sending}
          onChange={event => {setInput(event.target.value); setError("");}} placeholder={DEMO_INSTRUCTION}
          aria-describedby="chat-help" required />
        <p className="helper-text" id="chat-help">Sent messages stay in the conversation. New answers add to the same session.</p>
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <button type="submit" className="button button-primary" disabled={sending}>{sending ? "Checking details…" : "Send message"}</button>
      <p className="form-note">Demo data only. No candidate information or secrets. Review before publishing.</p>
    </form>
  </section>;
}
