import { useState } from "react";
import RecruiterChat from "./components/RecruiterChat";
import { RecruiterChatPage } from "./components/chatPresentation";
import CvIntake from "./components/CvIntake";
import { WorkspaceNavigation } from "./components/cvIntakePresentation";
import type { WorkspaceMode } from "./components/cvIntakePresentation";
import type { WorkingCriteriaDraft } from "./types/recruiterChat";

export default function App() {
  const [mode, setMode] = useState<WorkspaceMode>("jd");
  const [drafts, setDrafts] = useState<Record<string, WorkingCriteriaDraft>>({});
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const activeDraft = activeDraftId ? drafts[activeDraftId] ?? null : null;
  function updateDraft(draftId: string, update: (draft: WorkingCriteriaDraft) => WorkingCriteriaDraft) {
    setDrafts(current => current[draftId] ? {...current, [draftId]: update(current[draftId])} : current);
  }
  return <>
    <WorkspaceNavigation mode={mode} onChange={setMode} />
    <div hidden={mode !== "jd"}><RecruiterChatPage><RecruiterChat drafts={drafts}
      onDraftGenerated={draft => {setDrafts(current => ({...current, [draft.draftId]: draft})); setActiveDraftId(draft.draftId);}}
      onCriteriaChange={(id, criteria) => updateDraft(id, draft => ({...draft, criteria, reviewed: false}))}
      onCriteriaReviewed={(id, reviewed) => updateDraft(id, draft => ({...draft, reviewed}))}
      onContinueToCv={id => {setActiveDraftId(id); setMode("cv");}} /></RecruiterChatPage></div>
    <div hidden={mode !== "cv"}><CvIntake draft={activeDraft}
      onCriteriaChange={criteria => activeDraftId && updateDraft(activeDraftId, draft => ({...draft, criteria, reviewed: false}))}
      onCriteriaReviewed={reviewed => activeDraftId && updateDraft(activeDraftId, draft => ({...draft, reviewed}))} /></div>
  </>;
}
