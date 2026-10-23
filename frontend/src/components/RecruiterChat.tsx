import { useEffect, useReducer, useRef, useState } from "react";
import type { FormEvent } from "react";
import { isValidRecruiterMessage, RecruiterChatRequestError, sendRecruiterMessage } from "../api/recruiterChat";
import { publishDraft } from "../api/jobPublishing";
import { listConversations, loadConversation } from "../api/jobs";
import type { ChatMessage, WorkingCriteriaDraft } from "../types/recruiterChat";
import { ChatMessageView, EmptyConversation, replyToChatMessage } from "./chatPresentation";
import { initialRecruiterChatState, recruiterChatReducer } from "../state/recruiterChatState";

const DEMO_INSTRUCTION = "Create a Backend AI Engineer JD for a team building FastAPI services. Responsibilities include building APIs and automated tests. Required skills are Python, FastAPI and PostgreSQL. No minimum experience required.";

interface SendAttempt {messageId: string; text: string; conversationId?: string; uncertain: boolean;}

export default function RecruiterChat({drafts, onDraftGenerated, onCriteriaChange, onCriteriaReviewed, onContinueToCv, onNewChat, onConversationLoaded, onBusyChange, initialConversationId}: {
  initialConversationId?:string;
  onBusyChange?: (busy:boolean)=>void;
  onConversationLoaded: (id: string) => void;
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
  const [conversations, setConversations] = useState<{id: string; expires_at: string}[]>([]);
  const [restoring, setRestoring] = useState(false);
  const [restoreFailed,setRestoreFailed] = useState(false);
  const unresolved=messages.some(message=>message.sendState==='uncertain');
  useEffect(()=>{onBusyChange?.(sending||restoring||publishingBusy||unresolved);},[sending,restoring,publishingBusy,unresolved,onBusyChange]);
  useEffect(() => {
    let active = true;
    void listConversations().then(rows => {if (active) setConversations(rows);}).catch(() => {});
    return () => {active = false;};
  }, [conversationId]);
  async function restore(id: string) {
    if (!id || pending.current || restoring || attempt.current?.uncertain) return;
    setRestoring(true);setRestoreFailed(false);
    try {
      const saved = await loadConversation(id);
      onConversationLoaded(id); attempt.current = null;
      dispatch({type: "conversation_restored", conversationId: id, messages: saved.turns.flatMap(turn => [
        {role: "recruiter" as const, text: turn.message, sendState: "sent" as const}, replyToChatMessage(turn.reply)])});
    } catch {setRestoreFailed(true);dispatch({type: "input_error", message: "Conversation could not be restored. Select another saved conversation or explicitly start a new chat."});}
    finally {setRestoring(false);}
  }
  useEffect(()=>{if(initialConversationId)void restore(initialConversationId);},[initialConversationId]);

  async function sendAttempt(current: SendAttempt) {
    if (pending.current || restoring || restoreFailed || publishingBusy) return;
    pending.current = true;
    attempt.current = current;
    dispatch({type: "send_started", messageId: current.messageId, text: current.text});
    try {
      const reply = await sendRecruiterMessage(current.text, current.conversationId);
      attempt.current = null;
      dispatch({type: "send_succeeded", messageId: current.messageId, submittedText: current.text,
        reply: {...replyToChatMessage(reply), sourceInstruction: current.text}, conversationId: reply.conversation_id});
      if (reply.status === "jd_generated") onDraftGenerated({draftId: reply.draft_id,
        jobReference: reply.job_reference ?? undefined, revision: reply.job_revision, origin: "job_description", suggestions: reply.screening_suggestions, sources: reply.screening_suggestion_sources,
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
      const result = await publishDraft(message.jobDescriptionResult, message.publishingContext, message.draftId);
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
    if (sending || restoring || attempt.current?.uncertain || !message.jobDescriptionResult) return;
    dispatch({type: "input_changed", value: ""});
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
    if (pending.current || restoring || restoreFailed) return;
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
    if (pending.current || restoring || publishingBusy) return;
    const unresolved = attempt.current;
    if (unresolved?.uncertain && !window.confirm("The server may have accepted the previous request. Starting a new chat and sending it again could create another draft. Continue?")) return;
    attempt.current = null;
    setRestoreFailed(false);
    dispatch({type: "new_chat", preserveInput: Boolean(unresolved)});
    onNewChat();
  }

  const latestDraft=messages.findLast(message=>message.jobDescriptionResult);
  return <section className={`card chat-card ${messages.length ? "has-messages" : "is-empty"}`} aria-labelledby="chat-title">
    <label className="saved-conversation">Saved conversations<select value={conversationId ?? ""} disabled={sending || restoring || publishingBusy} onChange={e => void restore(e.target.value)}>
      <option value="">Choose a conversation</option>{conversations.map((row, index) => <option key={row.id} value={row.id}>Conversation {index + 1} · {new Date(row.expires_at).toLocaleString()}</option>)}
    </select></label>
    <div className="card-header">
      <div><h2 id="chat-title">Create a job description</h2></div>
      <div className="chat-header-actions">
        <button type="button" className="button button-secondary" disabled={sending || restoring || publishingBusy} onClick={() => {dispatch({type: "input_changed", value: DEMO_INSTRUCTION});}}>Load demo</button>
        <button type="button" className="button button-secondary" disabled={sending || restoring || publishingBusy} onClick={startNewChat}>New chat</button>
      </div>
    </div>
    <div ref={history} className="chat-history" role="log" aria-label="Recruiter conversation" aria-live="polite">
      {messages.length ? messages.map((message, index) => {
        const draft = message.draftId ? drafts[message.draftId] : undefined;
        const outdated=!!message.jobDescriptionResult && message!==latestDraft;
        return <ChatMessageView key={message.localMessageId ?? `${message.role}-${index}`} message={message} criteriaDraft={draft}
          onCriteriaChange={draft ? criteria => onCriteriaChange(draft.draftId, criteria) : undefined}
          onCriteriaReviewed={draft ? reviewed => onCriteriaReviewed(draft.draftId, reviewed) : undefined}
          onContinue={draft && message.jobReference && draft.jobReference===message.jobReference && !outdated ? () => onContinueToCv(draft.draftId) : undefined}
          onPublish={outdated?undefined:() => void publish(index)} onRevise={outdated?undefined:() => revise(message)}
          onRetry={message.localMessageId ? () => retryMessage(message.localMessageId!) : undefined} actionsDisabled={sending || restoring || publishingBusy || outdated} />;
      }) : <EmptyConversation />}
      {sending && <p role="status">Checking the requirements you shared…</p>}
    </div>
    <form className="chat-composer" onSubmit={submit}>
      {latestDraft?.jobReference && latestDraft.jobRevision && <p className="chat-refinement-context">Refining {latestDraft.jobReference} · Revision {drafts[latestDraft.draftId??'']?.revision??latestDraft.jobRevision}. Describe only what should change in this conversation. Updated criteria must be reviewed and confirmed again.</p>}
      <div className="field">
        <label htmlFor="chat-message">Your job instruction</label>
        <textarea ref={composer} id="chat-message" rows={3} maxLength={4000} value={input} disabled={sending || restoring || restoreFailed || publishingBusy}
          onChange={event => dispatch({type: "input_changed", value: event.target.value})} placeholder={latestDraft?'Example: Change the required experience to 3 years and add Docker as a preferred skill.':DEMO_INSTRUCTION}
          aria-describedby="chat-help" required />
        <p className="helper-text" id="chat-help">{latestDraft?'Send a specific change to revise this saved job. Use New chat for a different role.':'Describe the role and required skills. Follow-up answers stay in this conversation.'}</p>
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <button type="submit" className="button button-primary" disabled={sending || restoring || restoreFailed || publishingBusy}>{restoring ? "Restoring conversation…" : sending ? "Checking details…" : latestDraft?'Send revision':'Send message'}</button>
      <p className="form-note">Demo data only. No candidate information or secrets. Review before publishing.</p>
    </form>
  </section>;
}
