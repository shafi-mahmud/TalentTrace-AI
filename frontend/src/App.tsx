import InterviewSchedulingPage from './components/InterviewSchedulingPage';
import type {InterviewSelection} from './components/SavedScores';
import {workspaceModeFromHash, workspaceHash} from './state/workspaceNavigation';
import TranscriptPanel from './components/TranscriptPanel';
import CandidateScheduling from './components/CandidateScheduling';
import { lazy, Suspense, useEffect, useReducer, useRef, useState } from "react";
import type {ReactNode} from "react";
import RecruiterSignIn from "./components/RecruiterSignIn";
import { listJobs, workingJob } from "./api/jobs";
import type { SavedJob } from "./api/jobs";
import RecruiterChat from "./components/RecruiterChat";
import { RecruiterChatPage } from "./components/chatPresentation";
import CvIntake from "./components/CvIntake";
import CandidateInterview from "./components/CandidateInterview";
import { takeInvitation } from "./api/livekitInterview";
const LiveInterviewPage=lazy(()=>import("./components/LiveInterviewPage"));
import type { Interview } from "./api/interviews";
import { WorkspaceNavigation } from "./components/cvIntakePresentation";
import { initialRecruiterWorkspaceState, recruiterWorkspaceReducer, restoreActiveJob, rememberActiveJob } from "./state/recruiterWorkspace";

function Workspace({recruiterId,accountControls}: {recruiterId: string;accountControls:ReactNode}) {
  const [schedulingVisited,setSchedulingVisited]=useState(()=>workspaceModeFromHash(window.location.hash)==="scheduling");
  const [selection,setSelection]=useState<InterviewSelection|null>(null);
  const [liveInterview,setLiveInterview]=useState<Interview|null>(null);
  const [savedJobs, setSavedJobs] = useState<SavedJob[]>([]);
  const [jobError, setJobError] = useState("");
  const [workspace, dispatch] = useReducer(recruiterWorkspaceReducer, recruiterId, id => ({...initialRecruiterWorkspaceState, mode: workspaceModeFromHash(window.location.hash), activeDraftId: restoreActiveJob(window.sessionStorage, id)}));
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
  function changeMode(mode: typeof workspace.mode) {
    if(mode==="scheduling")setSchedulingVisited(true);
    setLiveInterview(null); window.location.hash=workspaceHash(mode); dispatch({type:"mode_changed",mode});
  }
  function goToScheduling(value?:InterviewSelection) {if(value)setSelection(value); changeMode("scheduling");}
  useEffect(()=>{const changed=()=>{if(workspaceModeFromHash(window.location.hash)==="scheduling")setSchedulingVisited(true);setLiveInterview(null);dispatch({type:"mode_changed",mode:workspaceModeFromHash(window.location.hash)});};window.addEventListener("hashchange",changed);return()=>window.removeEventListener("hashchange",changed);},[]);
  useEffect(()=>{setSelection(null);},[activeDraftId,drafts[activeDraftId??""]?.revision,workspace.criteriaContextRevision]);
  useEffect(()=>{window.history.replaceState(null,"",window.location.pathname+window.location.search+"#"+workspaceHash(mode));},[mode]);
  const activeDraft = activeDraftId ? drafts[activeDraftId] ?? null : null;
  useEffect(()=>{setLiveInterview(current=>current && current.job_id!==activeDraftId ? null:current);},[activeDraftId]);
  return <>
    <WorkspaceNavigation mode={mode} onChange={changeMode} accountControls={accountControls} />
    {(mode!=="jd" || Boolean(liveInterview)) && <div className="active-job-bar"><label>Active job<select value={activeDraftId ?? ""} onChange={event => {
      setLiveInterview(null);
      const job = savedJobs.find(job => job.id === event.target.value);
      if (job) dispatch({type: "draft_generated", draft: workingJob(job)});
      else dispatch({type: "new_chat"});
    }}><option value="">New job / no active job</option>{savedJobs.map(job => <option key={job.id} value={job.id}>{job.job_title} · {job.job_reference}</option>)}</select></label>
      <button className="button button-secondary" onClick={() => {
        if (!activeDraft || window.confirm("Reload saved requirements? Unsaved edits will be replaced.")) refreshJobs(true);
      }}>Reload saved jobs</button>{jobError && <p role="alert">{jobError}</p>}
    </div>}
    {liveInterview && liveInterview.job_id===activeDraftId && <Suspense fallback={<p role="status">Loading interview page…</p>}><LiveInterviewPage jobId={liveInterview.job_id} interview={liveInterview} onBack={()=>setLiveInterview(null)} /></Suspense>}
    <div hidden={Boolean(liveInterview) || mode !== "jd"}><RecruiterChatPage><RecruiterChat drafts={drafts}
      onDraftGenerated={draft => {dispatch({type: "draft_generated", draft}); refreshJobs();}}
      onConversationLoaded={id => {const job = savedJobs.find(job => job.conversation_id === id); if (job) dispatch({type: "draft_generated", draft: workingJob(job)});}}
      onCriteriaChange={(draftId, criteria) => dispatch({type: "criteria_changed", draftId, criteria})}
      onCriteriaReviewed={(draftId, reviewed) => dispatch({type: "criteria_reviewed", draftId, reviewed})}
      onContinueToCv={draftId => dispatch({type: "continue_to_screening", draftId})}
      onNewChat={() => dispatch({type: "new_chat"})} /></RecruiterChatPage></div>
    <div hidden={Boolean(liveInterview) || mode !== "cv"}><CvIntake draft={activeDraft} contextResetKey={workspace.criteriaContextRevision}
      onGoToScheduling={goToScheduling}
      onJobSaved={job => {dispatch({type: "draft_generated", draft: workingJob(job)}); refreshJobs();}}
      onCriteriaChange={criteria => activeDraftId && dispatch({type: "criteria_changed", draftId: activeDraftId, criteria})}
      onCriteriaReviewed={reviewed => activeDraftId && dispatch({type: "criteria_reviewed", draftId: activeDraftId, reviewed})} /></div>
    <div hidden={Boolean(liveInterview) || mode !== "scheduling"}>{schedulingVisited && <InterviewSchedulingPage draft={activeDraft} selection={selection} onSelect={setSelection} onOpenInterview={setLiveInterview} />}</div>
  </>;
}

export default function App({initialInvitation=null}:{initialInvitation?:string|null}) {
  const [invitationContext,setInvitationContext]=useState({token:initialInvitation,revision:0});
  useEffect(()=>{const changed=()=>{if(window.location.pathname==="/interview-join"){
    const token=takeInvitation(window.location,window.history);
    setInvitationContext(previous=>({token,revision:previous.revision+1}));
  }};window.addEventListener("hashchange",changed);return()=>window.removeEventListener("hashchange",changed);},[]);
  if(window.location.pathname==="/transcript-privacy")return <TranscriptPanel candidate={true} privacyOnly={true}/>;
  if(window.location.pathname==="/interview-schedule")return <CandidateScheduling />;
  if(window.location.pathname==="/interview-join")return <CandidateInterview key={invitationContext.revision} initialToken={invitationContext.token} />;
  return <RecruiterSignIn>{(user,accountControls) => <Workspace recruiterId={user.id} accountControls={accountControls} />}</RecruiterSignIn>;
}
