import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import {bookingReview,scheduleSummary} from '../src/components/schedulingReview.ts';
import {ScheduleForm,SavedInterviews} from '../src/components/InterviewScheduling.ts';
import type {CandidateScore,ScoringBatch} from '../src/types/screening';
const id='00000000-0000-4000-8000-000000000001';
const candidate:CandidateScore={job_reference:'TT-JOB-0000000000000001',upload_id:id,screening_decision:'eligible',status:'not_evaluated',reason:'uncertain_evidence',weights:{skill:50,experience:30,education:20},score:null,dimensions:[]};
const batch:ScoringBatch={job_id:id,job_reference:candidate.job_reference,batch_id:id,criteria_revision:2,scoring_version:'f2-coverage-v1',weights:candidate.weights,candidates:[candidate],ranking:[]};
const review=()=>bookingReview(id,2,batch,candidate,'2099-11-20T15:00','Asia/Dhaka',60,true);
test('review has exact job/application/revision and timezone-correct start and end',()=>{
 const r=review();assert.equal(r.request.scheduled_at,'2099-11-20T09:00:00.000Z');
 assert.equal(r.jobReference,batch.job_reference);assert.equal(r.request.upload_id,id);
 const summary=scheduleSummary(r.request.scheduled_at,'Asia/Dhaka',60);
 assert.match(summary,/3:00 PM/);assert.match(summary,/4:00 PM/);assert.match(summary,/Asia\/Dhaka/);
});
test('review rejects foreign, stale, unrelated, excluded, failed and unacknowledged selection',()=>{
 const reject=(b=batch,c=candidate,job=id,revision=2,ack=true)=>assert.throws(()=>bookingReview(job,revision,b,c,'2099-11-20T15:00','Asia/Dhaka',60,ack));
 reject(batch,candidate,'foreign');reject(batch,candidate,id,3);reject({...batch,candidates:[]});
 const excluded={...candidate,screening_decision:'excluded' as const};reject({...batch,candidates:[excluded]},excluded);
 const failed={...candidate,reason:'screening_incomplete' as const};reject({...batch,candidates:[failed]},failed);
 reject(batch,candidate,id,2,false);reject(batch,{...candidate});
 const foreign={...candidate,job_reference:'TT-JOB-0000000000000002'};reject({...batch,candidates:[foreign]},foreign);
});
test('preview does not book; confirmation is separate and contains no notification promise',()=>{
 const props={candidate,start:'2099-11-20T15:00',zone:'Asia/Dhaka',duration:60,confirmed:true,busy:false,alreadyScheduled:false,onStart(){},onZone(){},onDuration(){},onConfirmed(){},onSubmit(){}};
 const before=renderToStaticMarkup(h(ScheduleForm,props));assert.match(before,/Review interview/);assert.doesNotMatch(before,/Confirm booking/);
 const after=renderToStaticMarkup(h(ScheduleForm,{...props,review:review()}));
 for(const text of ['TT-JOB-0000000000000001','Application','batch','Start:','End:','No invitation or email','Edit booking'])assert.ok(after.includes(text),text);
 assert.match(after,/disabled=""[^>]*>Confirm booking/);
 const confirmed=renderToStaticMarkup(h(ScheduleForm,{...props,review:review(),finalConfirmed:true}));assert.doesNotMatch(confirmed,/disabled=""[^>]*>Confirm booking/);
});
test('saved schedule reload summary retains reference, end, timezone and application',()=>{
 const r=review();const html=renderToStaticMarkup(h(SavedInterviews,{criteriaRevision:2,rows:[{...r.request,id,job_id:id,job_reference:r.jobReference,status:'scheduled',unscored_confirmed:true}]}));
 for(const text of [r.jobReference,'4:00 PM','Asia/Dhaka',id,'Unscored selection confirmed'])assert.ok(html.includes(text));
});

// Execute the component's real handlers with mocked React hooks and API boundaries.
function harness(fail=false,existing=false,loadFails=false){
 const states:any[]=[],refs:any[]=[],effects:Array<()=>void>=[];let si=0,ri=0,first=true,writes=0,reads=0;
 const hooks={createElement:h,useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(x:any)=>states[i]=typeof x==='function'?x(states[i]):x];},useRef(v:any){return refs[ri++]??(refs[ri-1]={current:v});},useLayoutEffect(f:()=>void){if(first)effects.push(f);},useEffect(f:()=>void){if(first)effects.push(f);}};
 const request=review().request;
 const saved={...request,id,job_id:id,job_reference:batch.job_reference,status:'scheduled',unscored_confirmed:true};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/InterviewScheduling.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const require=createRequire(import.meta.url),exports:any={};
 runInNewContext(source,{exports,require:(name:string)=>name==='react'?hooks:name==='../api/interviews.ts'?{
  async listInterviews(){reads++;if(loadFails)throw Error('Unavailable');return existing || writes?[saved]:[];},async createInterview(job:string,body:any){writes++;assert.equal(job,id);assert.equal(body.scheduled_at,request.scheduled_at);if(fail)throw Error('Scheduling was not confirmed. Reload saved interviews.');return saved;}
 }:name==='./schedulingReview.ts'?{bookingReview,scheduleSummary}:name==='./interviewTime.ts'?{}:name==='./AppointmentEmail.ts'?{}:name==='./ConsolidatedAssessment.ts'?{}:require(name)});
 function render(){si=0;ri=0;const tree=exports.InterviewScheduling({jobId:id,criteriaRevision:2,scoring:batch,candidate});if(first){first=false;effects.forEach(f=>f());}return tree;}
 const form=()=>render().props.children[1].props;
 const submit=()=>form().onSubmit({preventDefault(){}});
 const tick=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
 return {render,form,submit,tick,get writes(){return writes;},get reads(){return reads;}};
}
test('real handlers require preview and final acknowledgement, then create exactly once',async()=>{
 const x=harness();x.render();await x.tick();let f=x.form();f.onStart('2099-11-20T15:00');f.onZone('Asia/Dhaka');f.onDuration(60);f.onConfirmed(true);
 await x.submit();assert.equal(x.writes,0);assert.ok(x.form().review);
 await x.submit();assert.equal(x.writes,0);
 x.form().onFinalConfirmed(true);await x.submit();assert.equal(x.writes,1);
 await x.submit();assert.equal(x.writes,1);assert.equal(x.form().alreadyScheduled,true);
});
test('editing invalidates review; uncertain write cannot be repeated before saved-result reconciliation',async()=>{
 const x=harness(true);x.render();await x.tick();let f=x.form();f.onStart('2099-11-20T15:00');f.onZone('Asia/Dhaka');f.onDuration(60);f.onConfirmed(true);
 await x.submit();x.form().onDuration(30);assert.equal(x.form().review,null);
 x.form().onDuration(60);await x.submit();x.form().onFinalConfirmed(true);await x.submit();assert.equal(x.writes,1);
 await x.submit();assert.equal(x.writes,1);assert.equal(x.form().busy,true);
 const reload=x.render().props.children.find((n:any)=>n?.type==='button');await reload.props.onClick();await x.tick();
 assert.equal(x.reads,2);assert.equal(x.form().alreadyScheduled,true);await x.submit();assert.equal(x.writes,1);
});
test('already saved selection cannot create another interview',async()=>{
 const x=harness(false,true);x.render();await x.tick();assert.equal(x.form().alreadyScheduled,true);await x.submit();assert.equal(x.writes,0);
});
test('failed saved-schedule load blocks booking rather than assuming an empty calendar',async()=>{
 const x=harness(false,false,true);x.render();await x.tick();assert.equal(x.form().busy,true);
 await x.submit();assert.equal(x.writes,0);
});
