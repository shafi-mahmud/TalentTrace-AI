import type { WorkspaceMode } from "../components/cvIntakePresentation";
import type { WorkingCriteriaDraft } from "../types/recruiterChat";

export interface RecruiterWorkspaceState {
  mode: WorkspaceMode;
  drafts: Record<string, WorkingCriteriaDraft>;
  activeDraftId: string | null;
  criteriaContextRevision: number;
}

export const initialRecruiterWorkspaceState: RecruiterWorkspaceState = {
  mode: "jd", drafts: {}, activeDraftId: null, criteriaContextRevision: 0,
};

export type RecruiterWorkspaceAction =
  | {type: "mode_changed"; mode: WorkspaceMode}
  | {type: "saved_job_reloaded"; context: RecruiterWorkspaceState; draft: WorkingCriteriaDraft | null}
  | {type: "draft_generated"; draft: WorkingCriteriaDraft}
  | {type: "criteria_changed"; draftId: string; criteria: WorkingCriteriaDraft["criteria"]}
  | {type: "criteria_reviewed"; draftId: string; reviewed: boolean}
  | {type: "continue_to_screening"; draftId: string}
  | {type: "new_chat"};

export function recruiterWorkspaceReducer(state: RecruiterWorkspaceState, action: RecruiterWorkspaceAction): RecruiterWorkspaceState {
  switch (action.type) {
    case "saved_job_reloaded": {
      if (state.activeDraftId !== action.context.activeDraftId || state.criteriaContextRevision !== action.context.criteriaContextRevision ||
          (state.activeDraftId && state.drafts[state.activeDraftId] !== action.context.drafts[state.activeDraftId])) return state;
      return action.draft ? {...state, drafts: {...state.drafts, [action.draft.draftId]: action.draft}} : {...state, activeDraftId: null};
    }
    case "mode_changed": return {...state, mode: action.mode};
    case "draft_generated": return {...state, drafts: {...state.drafts, [action.draft.draftId]: action.draft}, activeDraftId: action.draft.draftId};
    case "criteria_changed": {
      const draft = state.drafts[action.draftId];
      return draft ? {...state, drafts: {...state.drafts, [action.draftId]: {...draft, criteria: action.criteria, reviewed: false, savedSnapshot: null}}} : state;
    }
    case "criteria_reviewed": {
      const draft = state.drafts[action.draftId];
      return draft ? {...state, drafts: {...state.drafts, [action.draftId]: {...draft, reviewed: action.reviewed}}} : state;
    }
    case "continue_to_screening": return {...state, activeDraftId: action.draftId, mode: "cv"};
    case "new_chat": return {...state, activeDraftId: null, mode: "jd", criteriaContextRevision: state.criteriaContextRevision + 1};
  }
}

// Only an owned job UUID is remembered; job contents and approval come from the server.
export function restoreActiveJob(storage: Pick<Storage, "getItem">, recruiterId: string): string | null {
  try {
    const id = storage.getItem(`talenttrace-active-job:${recruiterId}`);
    return id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) ? id : null;
  } catch {return null;}
}

export function rememberActiveJob(storage: Pick<Storage, "setItem" | "removeItem">, recruiterId: string, id: string | null): void {
  try {
    const key = `talenttrace-active-job:${recruiterId}`;
    if (id) storage.setItem(key, id); else storage.removeItem(key);
  } catch {/* Browser storage restrictions must not prevent working in the session. */}
}


export function criteriaSaveStatus(draft: WorkingCriteriaDraft): string {
  const changed = JSON.stringify(draft.criteria) !== JSON.stringify(draft.suggestions.criteria);
  return changed ? "Job saved - Criteria edits not saved" : draft.reviewed ? "Job saved - Requirements confirmed" : "Job saved - Review needed";
}
