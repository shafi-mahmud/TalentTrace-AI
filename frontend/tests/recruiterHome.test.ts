import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import RecruiterHome from '../src/components/RecruiterHome.ts';
import {listJobs,workingJob} from '../src/api/jobs.ts';
import type {SavedJob} from '../src/api/jobs.ts';
import {initialRecruiterWorkspaceState,recruiterWorkspaceReducer,rememberActiveJob,restoreActiveJob} from '../src/state/recruiterWorkspace.ts';
import {workspaceHash,workspaceModeFromHash} from '../src/state/workspaceNavigation.ts';

const jobs:SavedJob[]=[1,2].map(i=>({id:`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`,
 job_reference:`TT-JOB-${String(i).padStart(16,'0')}`,job_title:`Synthetic job ${i}`,revision:i,
 suggestions:{job_title:`Synthetic job ${i}`,criteria:[{criterion_id:'python',description:'Python',category:'skill',is_hard:true}]},
 sources:[],snapshot:null,draft:null,conversation_id:null}));
const base={jobs,activeJobId:jobs[0].id,loading:false,error:'',onReload(){},onCreate(){},onSelect(){},onOpen(){}};
function all(n:any,p:(n:any)=>boolean):any[]{if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(c=>all(c,p))];}

test('Home renders actual owned API jobs, references and honest statuses',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json(jobs);});
 const loaded=await listJobs();assert.equal(calls,1);
 const html=renderToStaticMarkup(h(RecruiterHome,{...base,jobs:loaded}));
 for(const j of jobs){assert.ok(html.includes(j.job_title));assert.ok(html.includes(j.job_reference));}
 assert.match(html,/Active job/);assert.match(html,/Revision 2/);assert.match(html,/criteria need review/);
 assert.doesNotMatch(html,/Candidates screened|Interviews completed|0 candidates/);
});
test('empty, loading and failed Home states do not invent jobs or show stale success',()=>{
 assert.match(renderToStaticMarkup(h(RecruiterHome,{...base,jobs:[]})),/No saved jobs yet/);
 assert.match(renderToStaticMarkup(h(RecruiterHome,{...base,loading:true})),/Loading your saved jobs/);
 const failed=renderToStaticMarkup(h(RecruiterHome,{...base,error:'Saved jobs could not be loaded.'}));
 assert.match(failed,/role="alert"/);assert.ok(!failed.includes(jobs[0].job_reference));
});
test('Home actions carry the exact job and preserve another job draft',()=>{
 let state=recruiterWorkspaceReducer(initialRecruiterWorkspaceState,{type:'draft_generated',draft:workingJob(jobs[0])});
 const first=state.drafts[jobs[0].id];const actions:string[]=[];
 const tree=RecruiterHome({...base,onSelect:job=>{state=recruiterWorkspaceReducer(state,{type:'draft_generated',draft:workingJob(job)});},onOpen:(job,mode)=>actions.push(job.id+':'+mode),onCreate:()=>actions.push('create'),onReload:()=>actions.push('reload')});
 const buttons=all(tree,n=>n.type==='button');
 buttons.find(n=>n.props.children==='Create Job through Chat').props.onClick();
 buttons.find(n=>n.props.children==='Reload saved jobs').props.onClick();
 buttons.filter(n=>n.props.children==='Select active job')[1].props.onClick();
 buttons.filter(n=>n.props.children==='Review criteria')[1].props.onClick();
 buttons.filter(n=>n.props.children==='Interview Scheduling')[1].props.onClick();
 assert.equal(state.activeDraftId,jobs[1].id);assert.equal(state.drafts[jobs[0].id],first);
 assert.deepEqual(actions,['create','reload',jobs[1].id+':cv',jobs[1].id+':scheduling']);
 const html=renderToStaticMarkup(h(RecruiterHome,{...base,busy:true}));assert.match(html,/<button[^>]*disabled/);
});
test('Home is the default route and active selection survives only for the same recruiter',()=>{
 assert.equal(workspaceModeFromHash(''),'home');assert.equal(workspaceModeFromHash('#home'),'home');
 for(const mode of ['home','jd','cv','scheduling'] as const)assert.equal(workspaceModeFromHash('#'+workspaceHash(mode)),mode);
 const values=new Map<string,string>();const storage={getItem:(k:string)=>values.get(k)??null,setItem:(k:string,v:string)=>values.set(k,v),removeItem:(k:string)=>values.delete(k)};
 rememberActiveJob(storage,'owner',jobs[1].id);assert.equal(restoreActiveJob(storage,'owner'),jobs[1].id);assert.equal(restoreActiveJob(storage,'other'),null);
});
test('Home API rejection stays sanitized and does not retry',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response('private error',{status:401});});
 await assert.rejects(listJobs(),/Job changes could not be confirmed/);assert.equal(calls,1);
});
test('Home treats server job titles as text',()=>{
 const html=renderToStaticMarkup(h(RecruiterHome,{...base,jobs:[{...jobs[0],job_title:'<script>example</script>'}]}));
 assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
});

test('Home provides a five-stage journey and honest next action from confirmed criteria',()=>{
 const html=renderToStaticMarkup(h(RecruiterHome,base));
 for(const label of ['Create Job','Review Applicants','Schedule Interview','Conduct Interview','Assessment'])assert.ok(html.includes(label));
 assert.match(html,/Screening criteria need review/);assert.match(html,/>Review criteria<\/button>/);
 const ready={...jobs[0],snapshot:{job_reference:jobs[0].job_reference,job_title:jobs[0].job_title,criteria_confirmed:true as const,criteria:jobs[0].suggestions.criteria}};
 assert.match(renderToStaticMarkup(h(RecruiterHome,{...base,jobs:[ready]})),/>Review applicants<\/button>/);
});

test('each Home job has one primary next action and secondary actions stay expandable',()=>{
 const tree=RecruiterHome(base);const cards=all(tree,n=>n.type==='article');assert.equal(cards.length,2);
 for(const card of cards){
  assert.equal(all(card,n=>n.type==='button'&&n.props.className==='button button-primary').length,1);
  const actions=all(card,n=>n.type==='details'&&n.props.className.includes('home-job-actions'));
  assert.equal(actions.length,1);assert.notEqual(actions[0].props.open,true);
  assert.equal(all(card,n=>n.type==='ol'&&n.props['aria-label']==='Saved job progress').length,1);
 }
});
