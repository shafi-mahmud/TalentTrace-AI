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
  | {type: "draft_generated"; draft: WorkingCriteriaDraft}
  | {type: "criteria_changed"; draftId: string; criteria: WorkingCriteriaDraft["criteria"]}
  | {type: "criteria_reviewed"; draftId: string; reviewed: boolean}
  | {type: "continue_to_screening"; draftId: string}
  | {type: "new_chat"};

export function recruiterWorkspaceReducer(state: RecruiterWorkspaceState, action: RecruiterWorkspaceAction): RecruiterWorkspaceState {
  switch (action.type) {
    case "mode_changed": return {...state, mode: action.mode};
    case "draft_generated": return {...state, drafts: {...state.drafts, [action.draft.draftId]: action.draft}, activeDraftId: action.draft.draftId};
    case "criteria_changed": {
      const draft = state.drafts[action.draftId];
      return draft ? {...state, drafts: {...state.drafts, [action.draftId]: {...draft, criteria: action.criteria, reviewed: false}}} : state;
    }
    case "criteria_reviewed": {
      const draft = state.drafts[action.draftId];
      return draft ? {...state, drafts: {...state.drafts, [action.draftId]: {...draft, reviewed: action.reviewed}}} : state;
    }
    case "continue_to_screening": return {...state, activeDraftId: action.draftId, mode: "cv"};
    case "new_chat": return {...state, activeDraftId: null, mode: "jd", criteriaContextRevision: state.criteriaContextRevision + 1};
  }
}
