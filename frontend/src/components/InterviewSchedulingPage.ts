import {createElement as h} from 'react';
import type {WorkingCriteriaDraft} from '../types/recruiterChat';
import type {Interview} from '../api/interviews';
import SavedScores from './SavedScores.ts';
import type {InterviewSelection} from './SavedScores.ts';
import BulkScheduling from './BulkScheduling.ts';
import {SchedulingInvite} from './CandidateScheduling.ts';
import {InterviewScheduling} from './InterviewScheduling.ts';

export function currentSelection(draft:WorkingCriteriaDraft|null, selection:InterviewSelection|null) {
  return draft?.reviewed && draft.savedSnapshot && selection?.batch.job_id===draft.draftId &&
    selection.batch.criteria_revision===draft.revision && selection.candidate.screening_decision==='eligible' &&
    selection.batch.candidates.includes(selection.candidate) ? selection : null;
}

export default function InterviewSchedulingPage({draft,selection,onSelect,onOpenInterview}: {
  draft:WorkingCriteriaDraft|null; selection:InterviewSelection|null;
  onSelect:(selection:InterviewSelection)=>void; onOpenInterview:(interview:Interview)=>void;
}) {
  const selected=currentSelection(draft,selection);
  return h('div',{className:'app-shell recruiter-page scheduling-page'},h('main',null,
    h('div',{className:'page-intro'},h('p',{className:'eyebrow'},'Recruiter workspace'),
      h('h1',null,'Interview Scheduling'),h('p',{className:'page-description'},'Review eligible candidates, manage invitations and open your scheduled interviews.')),
    !draft ? h('p',{className:'card empty-state',role:'status'},'Select a saved job above to manage interview scheduling.') :
    !draft.reviewed || !draft.savedSnapshot || !draft.revision ? h('p',{className:'card empty-state',role:'status'},'Confirm the current job requirements in Candidate Screening before scheduling.') :
    h('div',{className:'scheduling-sections'},
      h('p',{className:'session-confirmation'},`${draft.jobReference} · Confirmed criteria revision ${draft.revision}`),
      h(BulkScheduling,{jobId:draft.draftId,revision:draft.revision}),
      h(SavedScores,{jobId:draft.draftId,revision:draft.revision,onSelectCandidate:onSelect}),
      h(InterviewScheduling,{jobId:draft.draftId,criteriaRevision:draft.revision,scoring:selected?.batch??null,candidate:selected?.candidate??null,onOpenInterview}),
      selected && h('section',{className:'card selected-candidate','aria-label':'Selected candidate invitation'},
        h('h2',null,'Alternative: candidate chooses a slot'),h('p',null,`Candidate reference: ${selected.candidate.upload_id.slice(0,8)}`),
        h(SchedulingInvite,{key:selected.batch.batch_id+selected.candidate.upload_id,batch:selected.batch,candidate:selected.candidate})))));
}
