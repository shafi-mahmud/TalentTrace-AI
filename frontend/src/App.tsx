import { lazy, Suspense, useEffect, useReducer, useRef, useState } from "react";
import RecruiterSignIn from "./components/RecruiterSignIn";
import { listJobs, workingJob } from "./api/jobs";
import type { SavedJob } from "./api/jobs";
import RecruiterChat from "./components/RecruiterChat";
import { RecruiterChatPage } from "./components/chatPresentation";
import CvIntake from "./components/CvIntake";
const LiveInterviewPage=lazy(()=>import("./components/LiveInterviewPage"));
import type { Interview } from "./api/interviews";
import { WorkspaceNavigation } from "./components/cvIntakePresentation";
import { initialRecruiterWorkspaceState, recruiterWorkspaceReducer, restoreActiveJob, rememberActiveJob } from "./state/recruiterWorkspace";

function Workspace({recruiterId}: {recruiterId: string}) {
  const [liveInterview,setLiveInterview]=useState<Interview|null>(null);
  const [savedJobs, setSavedJobs] = useState<SavedJob[]>([]);
  const [jobError, setJobError] = useState("");
  const [workspace, dispatch] = useReducer(recruiterWorkspaceReducer, recruiterId, id => ({...initialRecruiterWorkspaceState, activeDraftId: restoreActiveJob(window.sessionStorage, id)}));
  const {mode, drafts, activeDraftId} = workspace;
  const currentWorkspace = useRef(workspace);
  currentWorkspace.current = workspace;
  const loadSequence = useRef(0);
  function refreshJobs(reloadActive = false) {
    const context = currentWorkspace.current;
    const sequence = ++loadSequence.current;
    void listJobs().then(jobs => {
      if (sequence !== loadSequence.current) return;
      setSavedJobs(jobs); setJobError("");
      if (reloadActive && context.activeDraftId) {
        const job = jobs.find(job => job.id === context.activeDraftId);
        dispatch({type: "saved_job_reloaded", context, draft: job ? workingJob(job) : null});
      }
    }).catch(() => {if (sequence === loadSequence.current) setJobError("Saved jobs could not be loaded.");});
  }
  useEffect(() => {refreshJobs(true); return () => {loadSequence.current++;};}, []);
  useEffect(() => {rememberActiveJob(window.sessionStorage, recruiterId, activeDraftId);}, [recruiterId, activeDraftId]);
  const activeDraft = activeDraftId ? drafts[activeDraftId] ?? null : null;
  useEffect(()=>{setLiveInterview(current=>current && current.job_id!==activeDraftId ? null:current);},[activeDraftId]);
  return <>
    <WorkspaceNavigation mode={mode} onChange={mode => {setLiveInterview(null);dispatch({type: "mode_changed", mode});}} />
    <div className="active-job-bar"><label>Active job<select value={activeDraftId ?? ""} onChange={event => {
      setLiveInterview(null);
      const job = savedJobs.find(job => job.id === event.target.value);
      if (job) dispatch({type: "draft_generated", draft: workingJob(job)});
      else dispatch({type: "new_chat"});
    }}><option value="">New job / no active job</option>{savedJobs.map(job => <option key={job.id} value={job.id}>{job.job_title} · {job.job_reference}</option>)}</select></label>
      <button className="button button-secondary" onClick={() => {
        if (!activeDraft || window.confirm("Reload saved requirements? Unsaved edits will be replaced.")) refreshJobs(true);
      }}>Reload saved jobs</button>{jobError && <p role="alert">{jobError}</p>}
    </div>
    {liveInterview && liveInterview.job_id===activeDraftId && <Suspense fallback={<p role="status">Loading interview page…</p>}><LiveInterviewPage jobId={liveInterview.job_id} interview={liveInterview} onBack={()=>setLiveInterview(null)} /></Suspense>}
    <div hidden={Boolean(liveInterview) || mode !== "jd"}><RecruiterChatPage><RecruiterChat drafts={drafts}
      onDraftGenerated={draft => {dispatch({type: "draft_generated", draft}); refreshJobs();}}
      onConversationLoaded={id => {const job = savedJobs.find(job => job.conversation_id === id); if (job) dispatch({type: "draft_generated", draft: workingJob(job)});}}
      onCriteriaChange={(draftId, criteria) => dispatch({type: "criteria_changed", draftId, criteria})}
      onCriteriaReviewed={(draftId, reviewed) => dispatch({type: "criteria_reviewed", draftId, reviewed})}
      onContinueToCv={draftId => dispatch({type: "continue_to_screening", draftId})}
      onNewChat={() => dispatch({type: "new_chat"})} /></RecruiterChatPage></div>
    <div hidden={Boolean(liveInterview) || mode !== "cv"}><CvIntake draft={activeDraft} contextResetKey={workspace.criteriaContextRevision}
      onOpenInterview={setLiveInterview}
      onJobSaved={job => {dispatch({type: "draft_generated", draft: workingJob(job)}); refreshJobs();}}
      onCriteriaChange={criteria => activeDraftId && dispatch({type: "criteria_changed", draftId: activeDraftId, criteria})}
      onCriteriaReviewed={reviewed => activeDraftId && dispatch({type: "criteria_reviewed", draftId: activeDraftId, reviewed})} /></div>
  </>;
}

export default function App() {
  return <RecruiterSignIn>{user => <Workspace recruiterId={user.id} />}</RecruiterSignIn>;
}
