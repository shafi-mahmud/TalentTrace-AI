import {createElement as h} from 'react';
import type {SavedJob} from '../api/jobs';
import type {WorkspaceMode} from './cvIntakePresentation';

export default function RecruiterHome({jobs,activeJobId,loading,error,busy=false,onReload,onCreate,onSelect,onOpen}: {
  jobs:SavedJob[]; activeJobId:string|null; loading:boolean; error:string; busy?:boolean;
  onReload:()=>void; onCreate:()=>void; onSelect:(job:SavedJob)=>void;
  onOpen:(job:SavedJob,mode:WorkspaceMode)=>void;
}) {
  return h('main',{className:'app-shell recruiter-home'},
    h('section',{className:'card home-welcome'},
      h('div',null,h('p',{className:'eyebrow'},'Recruiter workspace'),h('h1',null,'Welcome to TalentTrace AI'),
        h('p',{className:'page-description'},'Start with a conversation. Return to your saved jobs and continue where you left off.')),
      h('button',{type:'button',className:'button button-primary',disabled:busy,onClick:onCreate},'Create Job through Chat')),
    busy ? h('p',{role:'status',className:'helper-text'},'Finish or reconcile the current conversation in JD Assistant before switching jobs or starting another chat.') : null,
    h('section',{'aria-labelledby':'home-jobs-title'},
      h('div',{className:'home-section-heading'},h('div',null,h('h2',{id:'home-jobs-title'},'Your saved jobs'),
        h('p',{className:'helper-text'},'Only jobs available to your signed-in recruiter account. Criteria status comes from the saved job; candidate and interview totals are not loaded here.')),
        h('button',{type:'button',className:'button button-secondary',disabled:loading,onClick:onReload},loading?'Loading jobs…':'Reload saved jobs')),
      error ? h('p',{role:'alert',className:'error-banner'},error) : loading ? h('p',{role:'status'},'Loading your saved jobs…') :
      !jobs.length ? h('div',{className:'card empty-state'},h('h3',null,'Your workspace is ready'),h('p',null,'No saved jobs yet. Create your first job through chat.')) :
      h('div',{className:'home-job-grid'},...jobs.map(job=>h('article',{key:job.id,className:`card home-job${job.id===activeJobId?' is-active':''}`},
        h('div',{className:'home-job-heading'},h('h3',null,job.job_title),job.id===activeJobId?h('span',{className:'review-badge'},'Active job'):null),
        h('p',{className:'home-job-reference'},h('span',null,'Job Reference'),h('strong',null,job.job_reference)),
        h('p',{className:'helper-text'},`Revision ${job.revision} · ${job.snapshot?'Screening criteria confirmed':'Screening criteria need review'}`),
        h('div',{className:'button-row'},
          h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>onSelect(job),'aria-pressed':job.id===activeJobId},'Select active job'),
          h('button',{type:'button',className:'button button-primary',disabled:busy,onClick:()=>onOpen(job,'cv')},'Continue Screening'),
          h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>onOpen(job,'scheduling')},'Interview Scheduling')))))));
}
