import assert from "node:assert/strict";
import { test } from "node:test";
import { initialRecruiterChatState, recruiterChatReducer } from "../src/state/recruiterChatState.ts";
import { initialRecruiterWorkspaceState, recruiterWorkspaceReducer } from "../src/state/recruiterWorkspace.ts";
import type { ChatMessage, WorkingCriteriaDraft } from "../src/types/recruiterChat.ts";

function draft(draftId: string): WorkingCriteriaDraft {
  return {draftId, origin: "job_description", suggestions: {job_title: "Engineer", criteria: []},
    sources: [], criteria: [], reviewed: true};
}

test("New chat clears active JD selection and advances screening context while retaining historical drafts", () => {
  const previous = recruiterWorkspaceReducer(initialRecruiterWorkspaceState, {type: "draft_generated", draft: draft("old-draft")});
  const screening = recruiterWorkspaceReducer(previous, {type: "continue_to_screening", draftId: "old-draft"});
  const next = recruiterWorkspaceReducer(screening, {type: "new_chat"});
  assert.equal(next.activeDraftId, null);
  assert.equal(next.mode, "jd");
  assert.equal(next.criteriaContextRevision, screening.criteriaContextRevision + 1);
  assert.equal(next.drafts["old-draft"].draftId, "old-draft");
});

test("successful message delivery clears only the submitted composer text", () => {
  const text = "Create a Backend Engineer JD.";
  let state = {...initialRecruiterChatState, input: text};
  state = recruiterChatReducer(state, {type: "send_started", messageId: "turn-1", text});
  const assistant: ChatMessage = {role: "assistant", text: "What responsibilities should I include?"};
  state = recruiterChatReducer(state, {type: "send_succeeded", messageId: "turn-1", submittedText: text,
    reply: assistant, conversationId: "conversation-1"});
  assert.equal(state.input, "");
  assert.equal(state.messages.filter(message => message.role === "recruiter").length, 1);
  assert.equal(state.messages[0].sendState, "sent");
});

test("failed send preserves composer text and marks delivery uncertain", () => {
  const text = "Create a Backend Engineer JD.";
  let state = {...initialRecruiterChatState, input: text};
  state = recruiterChatReducer(state, {type: "send_started", messageId: "turn-1", text});
  state = recruiterChatReducer(state, {type: "send_failed", messageId: "turn-1", text, message: "Connection lost.", uncertain: true, retryAvailable: false});
  assert.equal(state.input, text);
  assert.equal(state.messages[0].sendState, "uncertain");
  assert.equal(state.messages[0].retryAvailable, false);
});

test("retry updates the existing recruiter turn instead of appending a duplicate", () => {
  let state = {...initialRecruiterChatState, input: "First turn"};
  state = recruiterChatReducer(state, {type: "send_started", messageId: "turn-1", text: "First turn"});
  state = recruiterChatReducer(state, {type: "send_succeeded", messageId: "turn-1", submittedText: "First turn",
    reply: {role: "assistant", text: "Clarification"}, conversationId: "conversation-1"});
  state = {...state, input: "Follow-up"};
  state = recruiterChatReducer(state, {type: "send_started", messageId: "turn-2", text: "Follow-up"});
  state = recruiterChatReducer(state, {type: "send_failed", messageId: "turn-2", text: "Follow-up", message: "No confirmation.", uncertain: true, retryAvailable: true});
  state = recruiterChatReducer(state, {type: "send_started", messageId: "turn-2", text: "Follow-up"});
  state = recruiterChatReducer(state, {type: "send_succeeded", messageId: "turn-2", submittedText: "Follow-up",
    reply: {role: "assistant", text: "Draft unchanged"}, conversationId: "conversation-1"});
  assert.equal(state.messages.filter(message => message.role === "recruiter" && message.text === "Follow-up").length, 1);
  assert.equal(state.messages.length, 4);
  assert.equal(state.input, "");
});

test("starting over after an uncertain first request preserves input but clears the visible turn", () => {
  let state = {...initialRecruiterChatState, input: "Create a Backend Engineer JD."};
  state = recruiterChatReducer(state, {type: "send_started", messageId: "turn-1", text: state.input});
  state = recruiterChatReducer(state, {type: "send_failed", messageId: "turn-1", text: state.input, message: "May have completed.", uncertain: true, retryAvailable: false});
  state = recruiterChatReducer(state, {type: "new_chat", preserveInput: true});
  assert.equal(state.messages.length, 0);
  assert.equal(state.conversationId, undefined);
  assert.equal(state.input, "Create a Backend Engineer JD.");
});
