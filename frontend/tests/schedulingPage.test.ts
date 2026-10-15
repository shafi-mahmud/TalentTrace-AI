import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import InterviewSchedulingPage,{currentSelection} from '../src/components/InterviewSchedulingPage.ts';
import SavedScores from '../src/components/SavedScores.ts';
import {WorkspaceNavigation} from '../src/components/cvIntakePresentation.ts';
import {workspaceHash,workspaceModeFromHash} from '../src/state/workspaceNavigation.ts';
import {recruiterWorkspaceReducer,initialRecruiterWorkspaceState,restoreActiveJob} from '../src/state/recruiterWorkspace.ts';
import type {WorkingCriteriaDraft} from '../src/types/recruiterChat';
import type {InterviewSelection} from '../src/components/SavedScores';

const job='00000000-0000-4000-8000-000000000001';
const draft:WorkingCriteriaDraft={draftId:job,revision:2,origin:'manual',jobReference:'TT-JOB-0000000000000001',suggestions:{job_title:'Synthetic engineer',criteria:[]},criteria:[],sources:[],reviewed:true,savedSnapshot:{job_title:'Synthetic engineer',job_reference:'TT-JOB-0000000000000001',criteria_confirmed:true,criteria:[]}};
const candidate={job_reference:draft.jobReference!,upload_id:job,screening_decision:'eligible' as const,status:'not_evaluated' as const,reason:'uncertain_evidence' as const,weights:{skill:100,experience:0,education:0},score:null,dimensions:[]};
const selection:InterviewSelection={candidate,batch:{job_id:job,job_reference:draft.jobReference!,batch_id:job,criteria_revision:2,scoring_version:'f2-coverage-v1',weights:candidate.weights,candidates:[candidate],ranking:[]}};
const noop=()=>{};
test('three recruiter views and scheduling deep link retain job context',()=>{
 const html=renderToStaticMarkup(h(WorkspaceNavigation,{mode:'scheduling',onChange:noop}));
 assert.match(html,/aria-pressed="true">Interview Scheduling/);
 assert.match(html,/JD Assistant/);assert.match(html,/Candidate Screening/);
 assert.equal(workspaceModeFromHash('#'+workspaceHash('scheduling')),'scheduling');
 assert.equal(workspaceModeFromHash('#candidate-screening'),'cv');
 const state=recruiterWorkspaceReducer({...initialRecruiterWorkspaceState,activeDraftId:job,drafts:{[job]:draft}},{type:'mode_changed',mode:'scheduling'});
 assert.equal(state.activeDraftId,job);assert.equal(state.drafts[job],draft);
 assert.equal(restoreActiveJob({getItem:key=>key==='talenttrace-active-job:owner'?job:null},'other'),null);
});
test('screening saved-score view contains no invitation, booking or bulk controls',()=>{
 const html=renderToStaticMarkup(h(SavedScores,{jobId:job,revision:2,onSelectCandidate:noop}));
 assert.match(html,/Load saved scores/);assert.doesNotMatch(html,/Preview Invitations|Schedule interview|Send Scheduling Invitation|Reload saved interviews/);
});
test('scheduling page reuses invitations and has exactly one saved-interview section',()=>{
 const html=renderToStaticMarkup(h(InterviewSchedulingPage,{draft,selection,onSelect:noop,onOpenInterview:noop}));
 assert.match(html,/Confirmed criteria revision 2/);assert.match(html,/Preview Invitations/);
 assert.match(html,/Check saved operation status/);assert.match(html,/Generate scheduling invitation/);
 assert.match(html,/explicitly approve this eligible unscored/);
 assert.equal(html.split('Reload saved interviews').length-1,1);
 assert.match(html,/Loading saved interviews/);
});
test('no job and unconfirmed criteria show explicit safe empty states',()=>{
 const render=(d:WorkingCriteriaDraft|null)=>renderToStaticMarkup(h(InterviewSchedulingPage,{draft:d,selection,onSelect:noop,onOpenInterview:noop}));
 assert.match(render(null),/Select a saved job/);assert.doesNotMatch(render(null),/Preview Invitations/);
 assert.match(render({...draft,reviewed:false}),/Confirm the current job requirements/);
});
test('foreign, stale, excluded and unconfirmed candidate selections are discarded',()=>{
 assert.equal(currentSelection(draft,selection),selection);
 assert.equal(currentSelection({...draft,revision:3},selection),null);
 assert.equal(currentSelection({...draft,draftId:'foreign'},selection),null);
 assert.equal(currentSelection({...draft,reviewed:false},selection),null);
 assert.equal(currentSelection(draft,{...selection,candidate:{...candidate,screening_decision:'excluded'}}),null);
 assert.equal(currentSelection(draft,{...selection,batch:{...selection.batch,candidates:[]}}),null);
});
