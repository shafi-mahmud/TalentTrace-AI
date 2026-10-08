import { useEffect, useReducer, useRef, useState } from "react";
import type { FormEvent } from "react";
import { isValidRecruiterMessage, RecruiterChatRequestError, sendRecruiterMessage } from "../api/recruiterChat";
import { publishDraft } from "../api/jobPublishing";
import type { ChatMessage, WorkingCriteriaDraft } from "../types/recruiterChat";
import { ChatMessageView, replyToChatMessage } from "./chatPresentation";
import { initialRecruiterChatState, recruiterChatReducer } from "../state/recruiterChatState";

const DEMO_INSTRUCTION = "Create a Backend AI Engineer JD for a team building FastAPI services. Responsibilities include building APIs and automated tests. Required skills are Python, FastAPI and PostgreSQL. No minimum experience required.";

interface SendAttempt {messageId: string; text: string; conversationId?: string; uncertain: boolean;}

export default function RecruiterChat({drafts, onDraftGenerated, onCriteriaChange, onCriteriaReviewed, onContinueToCv, onNewChat}: {
  drafts: Record<string, WorkingCriteriaDraft>;
  onDraftGenerated: (draft: WorkingCriteriaDraft) => void;
  onCriteriaChange: (draftId: string, criteria: WorkingCriteriaDraft["criteria"]) => void;
  onCriteriaReviewed: (draftId: string, reviewed: boolean) => void;
  onContinueToCv: (draftId: string) => void;
  onNewChat: () => void;
}) {
  const [state, dispatch] = useReducer(recruiterChatReducer, initialRecruiterChatState);
  const {input, messages, error, sending, conversationId} = state;
  const [publishingBusy, setPublishingBusy] = useState(false);
  const pending = useRef(false);
  const attempt = useRef<SendAttempt | null>(null);
  const history = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const publishing = useRef(new Set<number>());

  async function sendAttempt(current: SendAttempt) {
    if (pending.current) return;
    pending.current = true;
    attempt.current = current;
    dispatch({type: "send_started", messageId: current.messageId, text: current.text});
    try {
      const reply = await sendRecruiterMessage(current.text, current.conversationId);
      attempt.current = null;
      dispatch({type: "send_succeeded", messageId: current.messageId, submittedText: current.text,
        reply: {...replyToChatMessage(reply), sourceInstruction: current.text}, conversationId: reply.conversation_id});
      if (reply.status === "jd_generated") onDraftGenerated({draftId: reply.draft_id,
        origin: "job_description", suggestions: reply.screening_suggestions, sources: reply.screening_suggestion_sources,
        criteria: reply.screening_suggestions.criteria.map(c => ({...c})), reviewed: false});
    } catch (failure) {
      const requestError = failure instanceof RecruiterChatRequestError ? failure
        : new RecruiterChatRequestError("Recruiter chat could not be completed. The request may have been received.", true, true);
      attempt.current = {...current, uncertain: requestError.uncertain};
      dispatch({type: "send_failed", messageId: current.messageId, text: current.text, message: requestError.message,
        uncertain: requestError.uncertain, retryAvailable: Boolean(current.conversationId) && requestError.retryable});
    } finally {
      pending.current = false;
    }
  }

  async function publish(index: number) {
    const message = messages[index];
    if (!message?.jobDescriptionResult || publishing.current.has(index) || (message.publication && message.publication.status !== "idle")) return;
    if (!window.confirm("Publish this reviewed synthetic demo draft to Discord? This sends a real message. Use demo data only.")) return;
    publishing.current.add(index);
    setPublishingBusy(true);
    dispatch({type: "replace_message", index, message: {...message, publication: {status: "loading"}}});
    try {
      const result = await publishDraft(message.jobDescriptionResult, message.publishingContext);
      dispatch({type: "replace_message", index, message: {...message, publication: {status: "success", result}}});
    } catch (failure) {
      const text = failure instanceof Error ? failure.message : "Publication was not confirmed. Check Discord before another attempt.";
      dispatch({type: "replace_message", index, message: {...message, publication: {status: "failed", message: text}}});
    } finally {
      publishing.current.delete(index);
      setPublishingBusy(publishing.current.size > 0);
    }
  }

  function revise(message: ChatMessage) {
    if (sending) return;
    dispatch({type: "input_changed", value: message.sourceInstruction ?? ""});
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
      dispatch({type: "input_error", message: "Enter job instructions of up to 4000 characters without unsafe control characters."});
      return;
    }
    const previous = attempt.current;
    if (previous?.uncertain && !previous.conversationId) {
      dispatch({type: "input_error", message: "The previous request may have completed. Start a new chat to continue; starting over may create another draft."});
      return;
    }
    if (previous?.uncertain && previous.text !== message) {
      dispatch({type: "input_error", message: "Retry the unconfirmed message in its existing conversation, or start a new chat."});
      return;
    }
    await sendAttempt({messageId: previous?.messageId ?? crypto.randomUUID(), text: message,
      conversationId: previous?.conversationId ?? conversationId, uncertain: false});
  }

  function retryMessage(messageId: string) {
    const previous = attempt.current;
    if (!previous || previous.messageId !== messageId || !previous.conversationId || pending.current) return;
    void sendAttempt(previous);
  }

  function startNewChat() {
    const unresolved = attempt.current;
    if (unresolved?.uncertain && !window.confirm("The server may have accepted the previous request. Starting a new chat and sending it again could create another draft. Continue?")) return;
    attempt.current = null;
    dispatch({type: "new_chat", preserveInput: Boolean(unresolved)});
    onNewChat();
  }

  return <section className="card chat-card" aria-labelledby="chat-title">
    <div className="card-header">
      <div><h2 id="chat-title">Recruiter chatbot</h2><p>Share requirements over a few messages. I’ll ask about anything missing.</p></div>
      <div className="chat-header-actions">
        <button type="button" className="button button-secondary" disabled={sending} onClick={() => {dispatch({type: "input_changed", value: DEMO_INSTRUCTION});}}>Load demo</button>
        <button type="button" className="button button-secondary" disabled={sending || publishingBusy} onClick={startNewChat}>New chat</button>
      </div>
    </div>
    <div ref={history} className="chat-history" role="log" aria-label="Recruiter conversation" aria-live="polite">
      {messages.length ? messages.map((message, index) => {
        const draft = message.draftId ? drafts[message.draftId] : undefined;
        return <ChatMessageView key={message.localMessageId ?? `${message.role}-${index}`} message={message} criteriaDraft={draft}
          onCriteriaChange={draft ? criteria => onCriteriaChange(draft.draftId, criteria) : undefined}
          onCriteriaReviewed={draft ? reviewed => onCriteriaReviewed(draft.draftId, reviewed) : undefined}
          onContinue={draft ? () => onContinueToCv(draft.draftId) : undefined}
          onPublish={() => void publish(index)} onRevise={() => revise(message)}
          onRetry={message.localMessageId ? () => retryMessage(message.localMessageId!) : undefined} actionsDisabled={sending} />;
      }) : <p className="helper-text">Start with a job title and purpose. I’ll gather responsibilities, skills and the experience requirement before drafting.</p>}
      {sending && <p role="status">Checking the requirements you shared…</p>}
    </div>
    <form className="chat-composer" onSubmit={submit}>
      <div className="field">
        <label htmlFor="chat-message">Your job instruction</label>
        <textarea ref={composer} id="chat-message" rows={3} maxLength={4000} value={input} disabled={sending}
          onChange={event => dispatch({type: "input_changed", value: event.target.value})} placeholder={DEMO_INSTRUCTION}
          aria-describedby="chat-help" required />
        <p className="helper-text" id="chat-help">Sent messages stay in the conversation. New answers add to the same session.</p>
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <button type="submit" className="button button-primary" disabled={sending}>{sending ? "Checking details…" : "Send message"}</button>
      <p className="form-note">Demo data only. No candidate information or secrets. Review before publishing.</p>
    </form>
  </section>;
}
