import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { isValidRecruiterMessage, sendRecruiterMessage } from "../api/recruiterChat";
import { publishDraft } from "../api/jobPublishing";
import type { ChatMessage } from "../types/recruiterChat";
import { ChatMessageView, replyToChatMessage } from "./chatPresentation";
import type { ScreeningSuggestions } from "../types/screening";

const DEMO_INSTRUCTION = "Create a Backend AI Engineer JD for a team building FastAPI services. Responsibilities include building APIs and automated tests. Required skills are Python, FastAPI and PostgreSQL.";

export default function RecruiterChat({onReviewCriteria}: {onReviewCriteria?: (suggestions: ScreeningSuggestions) => void}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const pending = useRef(false);
  const history = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const publishing = useRef(new Set<number>());

  async function publish(index: number) {
    const message = messages[index];
    if (!message?.jobDescriptionResult || publishing.current.has(index) || (message.publication && message.publication.status !== "idle")) return;
    if (!window.confirm("Publish this reviewed synthetic demo draft to Discord? This sends a real message. Use demo data only.")) return;
    publishing.current.add(index);
    setMessages(previous => previous.map((item, i) => i === index ? {...item, publication: {status: "loading"}} : item));
    try {
      const result = await publishDraft(message.jobDescriptionResult, message.publishingContext);
      setMessages(previous => previous.map((item, i) => i === index ? {...item, publication: {status: "success", result}} : item));
    } catch (failure) {
      const text = failure instanceof Error ? failure.message : "Publication was not confirmed. Check Discord before another attempt.";
      setMessages(previous => previous.map((item, i) => i === index ? {...item, publication: {status: "failed", message: text}} : item));
    }
    // Keep this card locked after the attempt: no implicit retries or double publication.
  }

  function revise(message: ChatMessage) {
    if (sending) return;
    setInput(message.sourceInstruction ?? "");
    setError("");
    composer.current?.focus();
  }
  useEffect(() => {
    // Scroll only this conversation, keeping the composer visible.
    const container = history.current;
    if (!container) return;
    if (messages.at(-1)?.jobDescriptionResult) {
      const cards = container.querySelectorAll<HTMLElement>(".chat-message");
      const latest = cards[cards.length - 1];
      if (latest) container.scrollTop += latest.getBoundingClientRect().top - container.getBoundingClientRect().top - 16;
    } else {
      container.scrollTop = container.scrollHeight;
    }
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
    setMessages((previous) => [...previous, { role: "recruiter", text: message }]);
    try {
      const reply = await sendRecruiterMessage(message);
      setMessages((previous) => [...previous, {...replyToChatMessage(reply), sourceInstruction: message}]);
      if (reply.status !== "clarification") setInput("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Recruiter chat could not be completed.");
    } finally {
      pending.current = false;
      setSending(false);
    }
  }

  return (
    <section className="card chat-card" aria-labelledby="chat-title">
      <div className="card-header">
        <div><h2 id="chat-title">Recruiter chatbot</h2><p>Describe the role. Review your policy-grounded draft right here.</p></div>
        <button type="button" className="button button-secondary" disabled={sending} onClick={() => { setInput(DEMO_INSTRUCTION); setError(""); }}>Load demo</button>
      </div>
      <div ref={history} className="chat-history" role="log" aria-label="Recruiter conversation" aria-live="polite">
        {messages.length ? messages.map((message, index) => <ChatMessageView key={index} message={message} onPublish={() => void publish(index)} onRevise={() => revise(message)}
          onReviewCriteria={message.screeningSuggestions && onReviewCriteria ? () => onReviewCriteria(message.screeningSuggestions!) : undefined} actionsDisabled={sending} />)
          : <p className="helper-text">Tell me the job title, role purpose, responsibilities and required skills. I’ll ask for missing information rather than invent it.</p>}
        {sending && <p role="status">Interpreting requirements and preparing your grounded draft…</p>}
      </div>
      <form className="chat-composer" onSubmit={submit}>
        <div className="field">
          <label htmlFor="chat-message">Your job instruction</label>
          <textarea ref={composer} id="chat-message" rows={3} maxLength={4000} value={input} disabled={sending}
            onChange={(event) => { setInput(event.target.value); setError(""); }} placeholder={DEMO_INSTRUCTION}
            aria-describedby="chat-help" required />
          <p className="helper-text" id="chat-help">Edit and resend your complete requirements after clarification or revision. Each request is independent.</p>
        </div>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button type="submit" className="button button-primary" disabled={sending}>{sending ? "Preparing JD draft…" : "Send instruction"}</button>
        <p className="form-note">Demo data only. No candidate information or secrets. Review before publishing.</p>
      </form>
    </section>
  );
}
