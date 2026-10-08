import { useReducer } from "react";
import RecruiterChat from "./components/RecruiterChat";
import { RecruiterChatPage } from "./components/chatPresentation";
import CvIntake from "./components/CvIntake";
import { WorkspaceNavigation } from "./components/cvIntakePresentation";
import { initialRecruiterWorkspaceState, recruiterWorkspaceReducer } from "./state/recruiterWorkspace";

export default function App() {
  const [workspace, dispatch] = useReducer(recruiterWorkspaceReducer, initialRecruiterWorkspaceState);
  const {mode, drafts, activeDraftId} = workspace;
  const activeDraft = activeDraftId ? drafts[activeDraftId] ?? null : null;
  return <>
    <WorkspaceNavigation mode={mode} onChange={mode => dispatch({type: "mode_changed", mode})} />
    <div hidden={mode !== "jd"}><RecruiterChatPage><RecruiterChat drafts={drafts}
      onDraftGenerated={draft => dispatch({type: "draft_generated", draft})}
      onCriteriaChange={(draftId, criteria) => dispatch({type: "criteria_changed", draftId, criteria})}
      onCriteriaReviewed={(draftId, reviewed) => dispatch({type: "criteria_reviewed", draftId, reviewed})}
      onContinueToCv={draftId => dispatch({type: "continue_to_screening", draftId})}
      onNewChat={() => dispatch({type: "new_chat"})} /></RecruiterChatPage></div>
    <div hidden={mode !== "cv"}><CvIntake draft={activeDraft} contextResetKey={workspace.criteriaContextRevision}
      onCriteriaChange={criteria => activeDraftId && dispatch({type: "criteria_changed", draftId: activeDraftId, criteria})}
      onCriteriaReviewed={reviewed => activeDraftId && dispatch({type: "criteria_reviewed", draftId: activeDraftId, reviewed})} /></div>
  </>;
}
