import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AssessmentView} from '../src/components/ConsolidatedAssessment.ts';
import {fetchReport,validReport,evidenceStates} from '../src/api/consolidatedAssessment.ts';
import type {ConsolidatedReport} from '../src/api/consolidatedAssessment';
import {SavedScoreCards} from '../src/components/SavedScores.ts';
const id='00000000-0000-4000-8000-000000000001';
function fixture():ConsolidatedReport {
 return {version:'f6-increment-1',job_id:id,job_title:'Synthetic Python developer',job_reference:'TT-JOB-0000000000000001',
 batch_id:id,upload_id:id,criteria_revision:2,cv_source:'interview_selection_snapshot',review_required:true,
 notice:'Recruiter review required. Missing evidence is not poor performance. No combined score.',
 cv:{job_reference:'TT-JOB-0000000000000001',upload_id:id,screening_decision:'eligible',status:'not_evaluated',
 reason:'uncertain_evidence',weights:{skill:100,experience:0,education:0},score:null,dimensions:[]},
 interview:{state:'missing_analysis',interview_id:id,operation_id:null,rubric_version:null,retention_deadline:null,warning:null,
 pairs:[],requirements:[],assessment:null,references:[],turns:[]}};
}
function complete():ConsolidatedReport {
 const r=fixture();r.interview={state:'available',interview_id:id,operation_id:id,rubric_version:'interview-evidence-v1',retention_deadline:new Date(Date.now()+60000).toISOString(),
 warning:'ASR unverified. Missing evidence is not lack of skill.',
 pairs:[{id,question:'What is Python?',answer:'Synthetic answer',question_turns:[id],answer_turns:[id],status:'answered',warnings:[],start_ms:0,end_ms:1000,capture_id:id}],
 requirements:[{criterion_id:'python',description:'Python',coverage:'partial',explanation:'Literal topic only.',follow_up:'Verify examples.',qa_ids:[id],turn_ids:[id]}],
 assessment:{answers:[{qa_id:id,dimensions:['relevance','technical_accuracy','completeness','articulation'].map(d=>({dimension:d,status:'supported',justification:'Saved interpretation.',evidence:[{turn_id:id,quote:'Synthetic answer'}]})),technical_citations:[],follow_up:'Verify details.'}]},
 references:[],turns:[{id,role:'candidate',text:'Synthetic answer',session_id:id,start_ms:0,end_ms:1000}]};return r;
}
test('missing evidence is explicit without zero scores or negative suitability',()=>{
 const r=fixture();assert.ok(validReport(r,id,id,id));const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
 assert.match(html,/No persisted interview analysis/);assert.match(html,/Missing evidence is not poor performance/);
 assert.doesNotMatch(html,/0.00 \/ 100|Reject candidate|Analyze interview/);
 assert.match(html,/Saved at interview selection/);
});
test('all unavailable states render without interview text',()=>{
 for(const state of evidenceStates.filter(s=>s!=='available')){
  const r=fixture();r.interview.state=state;assert.ok(validReport(r,id,id,id));
  const html=renderToStaticMarkup(h(AssessmentView,{report:r}));assert.doesNotMatch(html,/Saved interpretation|Synthetic answer/);
 }
});
test('saved F5 dimensions and coverage link to timestamped authorized turns',()=>{
 const r=complete();assert.ok(validReport(r,id,id,id));const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
 assert.match(html,/technical_accuracy/);assert.match(html,/Evidence-linked strength/);assert.match(html,/Literal topic only/);
 assert.match(html,/source turn/);assert.match(html,/0–1000 ms/);assert.match(html,/Synthetic answer/);
 const link=html.match(/href="#([^"]+)"/);assert.ok(link);assert.ok(html.includes(`id="${link[1]}"`));
});
test('wrong candidate, job, revision and hidden stale text are rejected',()=>{
 const r=fixture();assert.ok(!validReport(r,id,id,'foreign'));assert.ok(!validReport({...r,job_id:'foreign'},id,id,id));
 assert.ok(!validReport({...r,criteria_revision:0},id,id,id));
 assert.ok(!validReport({...r,interview:{...r.interview,turns:complete().interview.turns}},id,id,id));
 const expired=complete();expired.interview.retention_deadline=new Date(0).toISOString();assert.ok(!validReport(expired,id,id,id));
 const c=complete();c.interview.assessment!.answers[0].dimensions=[];assert.ok(!validReport(c,id,id,id));
});
test('report GET is credentialed, uncached and never posts or retries',async()=>{
 const old=globalThis.fetch;let calls=0;
 globalThis.fetch=async(url,init)=>{calls++;assert.match(String(url),/\/assessment$/);assert.equal(init?.method,undefined);
  assert.equal(init?.credentials,'include');assert.equal(init?.cache,'no-store');return new Response(JSON.stringify(fixture()));};
 try{assert.equal((await fetchReport(id,id,id)).version,'f6-increment-1');assert.equal(calls,1);}finally{globalThis.fetch=old;}
});
test('errors do not expose response text; aborted requests do not retry',async()=>{
 const old=globalThis.fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;return new Response('private candidate details',{status:403});};
 try{await assert.rejects(fetchReport(id,id,id),e=>e instanceof Error&&!e.message.includes('private candidate'));assert.equal(calls,1);}
 finally{globalThis.fetch=old;}
 const c=new AbortController();c.abort();
 globalThis.fetch=async(_url,init)=>{assert.equal(init?.signal,c.signal);throw new DOMException('Aborted','AbortError');};
 try{await assert.rejects(fetchReport(id,id,id,c.signal));}finally{globalThis.fetch=old;}
});
test('excluded and unscored saved candidates can open report without interview selection',()=>{
 const r=fixture();const html=renderToStaticMarkup(h(SavedScoreCards,{batches:[{job_id:id,job_reference:r.job_reference,batch_id:id,
 criteria_revision:2,scoring_version:'f2-coverage-v1',weights:r.cv.weights,candidates:[r.cv],ranking:[]}],onSelect:()=>{}}));
 assert.match(html,/View consolidated assessment/);
});

test('print view retains complete authorized findings and paper source identities',()=>{
 const r=complete();const html=renderToStaticMarkup(h(AssessmentView,{report:r,preparedAt:'2026-10-17T12:00:00.000Z'}));
 assert.match(html,/Print view prepared \(UTC\): 2026-10-17/);
 assert.match(html,/did not rerun screening or interview evaluation/);
 assert.match(html,/copies are outside application retention and cannot be revoked/);
 assert.match(html,/Requirement coverage and gaps/);assert.match(html,/technical_accuracy/);
 assert.match(html,new RegExp(`source turn ${id}`));assert.match(html,/capture/);
 assert.doesNotMatch(html,/<button|<input|<nav/);
});
test('print copy handles CV-only, missing F5, excluded and withdrawn evidence without fabrication',()=>{
 for(const state of ['not_scheduled','missing_analysis','withdrawn','expired','deleted'] as const){
  const r=fixture();r.interview.state=state;r.cv.screening_decision='excluded';r.cv.reason='not_eligible';
  const html=renderToStaticMarkup(h(AssessmentView,{report:r,preparedAt:'2026-10-17T12:00:00.000Z'}));
  assert.match(html,/excluded/);assert.match(html,/Recruiter review required/);
  assert.doesNotMatch(html,/Saved interpretation|Synthetic answer|0.00 \/ 100/);
 }
});
test('long synthetic reference text is preserved and escaped in printable content',()=>{
 const r=complete(),text='Long synthetic evidence with <script> text. '.repeat(30);
 r.interview.references=[{id:'synthetic-reference',topic:'Synthetic topic',text,provenance:'synthetic_demo'}];
 const html=renderToStaticMarkup(h(AssessmentView,{report:r,preparedAt:'2026-10-17T12:00:00Z'}));
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.equal((html.match(/Long synthetic evidence/g)??[]).length,30);
});
