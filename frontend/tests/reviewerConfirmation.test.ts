import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
import {saveConfirmation,validConfirmation,positionLabels} from '../src/api/reviewerConfirmation.ts';
import type {ConfirmationView} from '../src/api/reviewerConfirmation';
import type {ConsolidatedReport} from '../src/api/consolidatedAssessment';
import {AssessmentView} from '../src/components/ConsolidatedAssessment.ts';
import {ComparisonView} from '../src/components/CandidateComparison.ts';
import ReviewerConfirmation,{confirmationChoices} from '../src/components/ReviewerConfirmation.ts';
import {printAssessment} from '../src/api/assessmentPrinting.ts';
const id='00000000-0000-4000-8000-000000000001';
function confirmation():ConfirmationView{return {enabled:true,state:'confirmed',version:1,evidence_token:'a'.repeat(64),position:'alignment',scope:'cv_only',
 requirement_ids:['python'],references:[{criterion_id:'python',kind:'cv',reason:'supported_requirement',qa_id:null,dimension:null}],
 reviewer_id:id,confirmed_at:new Date().toISOString(),expires_at:new Date(Date.now()+60000).toISOString()};}
function report():ConsolidatedReport{return {version:'f6-increment-1',job_id:id,job_title:'Synthetic role',job_reference:'TT-JOB-0000000000000001',batch_id:id,upload_id:id,
 criteria_revision:2,cv_source:'current_saved_score',review_required:true,notice:'Missing evidence is not poor performance.',
 confirmed_requirements:[{criterion_id:'python',description:'Python programming',category:'skill',is_hard:true}],confirmation:confirmation(),
 cv:{job_reference:'TT-JOB-0000000000000001',upload_id:id,screening_decision:'eligible',status:'not_evaluated',reason:'uncertain_evidence',score:null,weights:{skill:100,experience:0,education:0},dimensions:[]},
 interview:{state:'not_scheduled',interview_id:null,operation_id:null,rubric_version:null,retention_deadline:null,warning:null,pairs:[],requirements:[],assessment:null,references:[],turns:[]}};}
test('confirmed, stale and restricted projections validate without hidden judgment payloads',()=>{
 assert.ok(validConfirmation(confirmation()));
 for(const state of ['stale','restricted','pending'] as const){const c={...confirmation(),state};assert.ok(!validConfirmation(c));
  assert.ok(validConfirmation({...c,position:null,scope:null,requirement_ids:[],references:[],reviewer_id:null,confirmed_at:null,expires_at:null}));}
 assert.ok(!validConfirmation({...confirmation(),expires_at:new Date(0).toISOString()}));
 assert.ok(!validConfirmation({...confirmation(),reviewer_id:'foreign'}));
 assert.ok(!validConfirmation({...confirmation(),references:[{...confirmation().references[0],criterion_id:'foreign'}]}));
});
test('all positions stay separate from scores and hiring decisions; print and comparison share them',()=>{
 for(const position of ['alignment','mixed','insufficient'] as const){
  const r=report();r.confirmation!.position=position;
  for(const html of [renderToStaticMarkup(h(AssessmentView,{report:r})),renderToStaticMarkup(h(AssessmentView,{report:r,preparedAt:new Date().toISOString()})),
   renderToStaticMarkup(h(ComparisonView,{comparison:{version:'f6-comparison-1',job_id:id,criteria_revision:2,reports:[r,structuredClone(r)],review_required:true,notice:'No ranking.'}}))]){
   assert.ok(html.includes(positionLabels[position]));assert.match(html,/CV-only reviewed scope/);assert.match(html,/Python programming/);
   assert.doesNotMatch(html,/0.00 \/ 100|Hire candidate|Reject candidate/);
  }
 }
});
test('stale and restricted reports disclose no active position or prior structured rationale',()=>{
 for(const state of ['stale','restricted'] as const){const r=report();r.confirmation={...confirmation(),state,position:null,scope:null,requirement_ids:[],references:[],reviewer_id:null,confirmed_at:null,expires_at:null};
  const html=renderToStaticMarkup(h(AssessmentView,{report:r}));assert.match(html,new RegExp(`Overall suitability position: ${state}`));
  assert.doesNotMatch(html,/Recruiter-confirmed suitability|Evidence supports alignment within reviewed scope|Supported requirement \(cv\)/);
 }
});
test('confirmation UI starts unselected, requires acknowledgment and retains mandatory scope',()=>{
 const r=report();const html=renderToStaticMarkup(h(ReviewerConfirmation,{report:r,refresh:()=>{},signal:new AbortController().signal}));
 assert.match(html,/Select a position/);assert.match(html,/I reviewed the original evidence/);assert.match(html,/mandatory/);assert.match(html,/disabled/);
 assert.doesNotMatch(html,/<textarea|type="text"/);assert.equal(confirmationChoices(r,'cv_only')[0].ref.kind,'gap');
 const disabled=report();disabled.confirmation!.enabled=false;assert.equal(renderToStaticMarkup(h(ReviewerConfirmation,{report:disabled,refresh:()=>{},signal:new AbortController().signal})), '');
});
test('explicit mutation sends one credentialed PUT; uncertain failures never retry or expose response text',async()=>{
 const old=fetch;let count=0;
 const body={expected_version:0,evidence_token:'a'.repeat(64),position:'alignment' as const,scope:'cv_only' as const,requirement_ids:['python'],references:confirmation().references};
 globalThis.fetch=async(url,init)=>{count++;assert.match(String(url),/assessment\/confirmation$/);assert.equal(init?.method,'PUT');assert.equal(init?.credentials,'include');assert.equal(init?.cache,'no-store');
  assert.equal(JSON.parse(String(init?.body)).expected_version,0);return new Response(JSON.stringify(confirmation()));};
 try{assert.equal((await saveConfirmation(id,id,id,body)).version,1);assert.equal(count,1);
  globalThis.fetch=async()=>{count++;return new Response('private detail',{status:503});};
  await assert.rejects(saveConfirmation(id,id,id,body),e=>e instanceof Error&&!e.message.includes('private detail'));assert.equal(count,2);
 }finally{globalThis.fetch=old;}
});
test('CV-only confirmation expiry also limits the prepared native print copy',async()=>{
 const r=report();let ttl=0,clear=()=>{};const c=new AbortController();
 await printAssessment(async()=>r,{now:()=>Date.now(),mount:()=>()=>{},print:()=>{},afterPrint:()=>()=>{},beforePrint:()=>()=>{},
  expireAfter:(ms,cb)=>{ttl=ms;clear=cb;return()=>{};},finished:()=>{}},c.signal);
 assert.ok(ttl>0&&ttl<=60000);clear();
});
test('mutation drafts use component memory and block resubmission after uncertainty',()=>{
 const source=readFileSync(new URL('../src/components/ReviewerConfirmation.ts',import.meta.url),'utf8');
 assert.match(source,/setLocked\(true\)/);assert.match(source,/Refresh and reconcile/);assert.doesNotMatch(source,/localStorage|sessionStorage|setInterval/);
});
