import type { ChatMessage } from "../types/recruiterChat";

export interface RecruiterChatState {
  input: string;
  messages: ChatMessage[];
  error: string;
  sending: boolean;
  conversationId?: string;
}

export const initialRecruiterChatState: RecruiterChatState = {input: "", messages: [], error: "", sending: false};

export type RecruiterChatAction =
  | {type: "input_changed"; value: string}
  | {type: "input_error"; message: string}
  | {type: "send_started"; messageId: string; text: string}
  | {type: "send_failed"; messageId: string; text: string; message: string; uncertain: boolean; retryAvailable: boolean}
  | {type: "send_succeeded"; messageId: string; submittedText: string; reply: ChatMessage; conversationId: string}
  | {type: "replace_message"; index: number; message: ChatMessage}
  | {type: "new_chat"; preserveInput: boolean}
  | {type: "conversation_restored"; conversationId: string; messages: ChatMessage[]};

export function recruiterChatReducer(state: RecruiterChatState, action: RecruiterChatAction): RecruiterChatState {
  switch (action.type) {
    case "conversation_restored": return {...state, input: "", error: "", sending: false, messages: action.messages, conversationId: action.conversationId};
    case "input_changed": return {...state, input: action.value, error: ""};
    case "input_error": return {...state, error: action.message};
    case "send_started": {
      const existing = state.messages.some(message => message.localMessageId === action.messageId);
      const messages = existing
        ? state.messages.map(message => message.localMessageId === action.messageId
          ? {...message, text: action.text, sendState: "sending" as const, sendError: undefined, retryAvailable: false} : message)
        : [...state.messages, {role: "recruiter" as const, localMessageId: action.messageId, text: action.text, sendState: "sending" as const}];
      return {...state, messages, error: "", sending: true};
    }
    case "send_failed": return {...state, messages: state.messages.map(message => message.localMessageId === action.messageId
      ? {...message, text: action.text, sendState: action.uncertain ? "uncertain" as const : "failed" as const,
        sendError: action.message, retryAvailable: action.retryAvailable} : message), error: "", sending: false};
    case "send_succeeded": {
      const messages = state.messages.map(message => message.localMessageId === action.messageId
        ? {...message, text: action.submittedText, sendState: "sent" as const, sendError: undefined, retryAvailable: false} : message);
      return {...state, messages: [...messages, action.reply], input: state.input.trim() === action.submittedText ? "" : state.input,
        error: "", sending: false, conversationId: action.conversationId};
    }
    case "replace_message": return {...state, messages: state.messages.map((message, index) => index === action.index ? action.message : message)};
    case "new_chat": return {...initialRecruiterChatState, input: action.preserveInput ? state.input : ""};
  }
}
