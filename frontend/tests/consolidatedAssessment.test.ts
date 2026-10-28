import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AssessmentView,focusAssessmentSource} from '../src/components/ConsolidatedAssessment.ts';
import {fetchReport,validReport,evidenceStates} from '../src/api/consolidatedAssessment.ts';
import type {ConsolidatedReport} from '../src/api/consolidatedAssessment';
import {SavedScoreCards} from '../src/components/SavedScores.ts';
import {ComparisonView} from '../src/components/CandidateComparison.ts';
const id='00000000-0000-4000-8000-000000000001';
test('source navigation opens evidence and transfers keyboard focus without adding a Tab stop',()=>{
 const old=Object.getOwnPropertyDescriptor(globalThis,'document');
 const order:string[]=[],details={open:false};
 const target={tabIndex:0,closest:()=>details,focus(options:{preventScroll:boolean}){assert.equal(details.open,true);assert.equal(options.preventScroll,true);order.push('focus');},scrollIntoView(){order.push('scroll');}};
 Object.defineProperty(globalThis,'document',{configurable:true,value:{getElementById:(id:string)=>id==='source'?target:null}});
 try{focusAssessmentSource('source');assert.equal(target.tabIndex,-1);assert.deepEqual(order,['focus','scroll']);focusAssessmentSource('missing');assert.equal(order.length,2);}
 finally{if(old)Object.defineProperty(globalThis,'document',old);else Reflect.deleteProperty(globalThis,'document');}
});
function fixture():ConsolidatedReport {
 return {version:'f6-increment-1',job_id:id,job_title:'Synthetic Python developer',job_reference:'TT-JOB-0000000000000001',
 batch_id:id,upload_id:id,confirmed_requirements:[],criteria_revision:2,cv_source:'interview_selection_snapshot',review_required:true,
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

function withRequirements(r=fixture()){
 r.confirmed_requirements=[{criterion_id:'python',description:'Python programming',category:'skill',is_hard:true},
  {criterion_id:'sql',description:'SQL transactions',category:'skill',is_hard:false}];
 return r;
}
test('profile separates pending judgment, component evidence and completeness with plain requirement names',()=>{
 const r=withRequirements();const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
 for(const text of ['Suitability evidence profile','Overall suitability position: pending recruiter confirmation.',
  'CV score','Interview findings','Evidence completeness','Python programming','SQL transactions','Requirement audit ID',
  'No persisted CV requirement evidence','not persisted for this unscored result'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/0.00 \/ 100|Suitable candidate|Reject candidate|Combined suitability score/);
});
test('profile indexes original CV scores and findings without inferring interview competence',()=>{
 const r=withRequirements(complete());r.cv={...r.cv,status:'scored',reason:null,score:100,dimensions:[
  {category:'skill',weight:100,supported_count:1,total_requirements:1,coverage_percent:100,weighted_points:100,
   matches:[{criterion_id:'python',match_status:'supported',match_method:'deterministic',explanation:'Original CV evidence.',evidence:[]}]}]};
 r.interview.assessment!.answers[0].dimensions[1].status='concern';
 const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
 for(const text of ['100.00 / 100','1 supported CV matches among 1 persisted','3 supported; 1 concern',
  'Demonstrated in saved CV','Literal topic evidence; competence not established','What is Python?',
  'Documented concern','Saved interpretation.','Original CV evidence.'])assert.ok(html.includes(text),text);
 for(const target of [...html.matchAll(/href="#([^"]+)"/g)])assert.ok(html.includes(`id="${target[1]}"`),target[1]);
 assert.doesNotMatch(html,/Overall suitability position: (supported|concern)|Recommended candidate/);
});
test('profile distinguishes no literal topic evidence from a negative performance finding',()=>{
 const r=withRequirements(complete());r.interview.requirements[0].coverage='not_evidenced';r.interview.requirements[0].qa_ids=[];
 const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
 assert.match(html,/No literal topic evidence; semantic coverage not assessed/);
 assert.match(html,/No saved interview mapping; not assessed/);
 assert.match(html,/Verify examples/);
});
test('profile never displays restricted F5 findings even if stale text remains in an input object',()=>{
 for(const state of evidenceStates.filter(s=>s!=='available')){
  const r=withRequirements(complete());r.interview.state=state;
  const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
  assert.match(html,/No authorized interview pairs are available/);
  assert.match(html,/Missing or restricted evidence is not poor performance/);
  assert.doesNotMatch(html,/Saved interpretation|Synthetic answer|What is Python|Verify examples/);
 }
});
test('historical description absence is explicit and never replaced by guessed names',()=>{
 const r=fixture();r.criteria_revision=1;r.interview.state='stale';
 const html=renderToStaticMarkup(h(AssessmentView,{report:r}));
 assert.match(html,/Confirmed requirement descriptions for this report revision are unavailable/);
 assert.match(html,/current names are not substituted/);
 assert.match(html,/No requirement-level evidence index can be assembled/);
});
test('new confirmed context is bounded, required and rejects duplicate or malformed requirement labels',()=>{
 const r=withRequirements();assert.ok(validReport(r,id,id,id));
 assert.ok(!validReport({...r,confirmed_requirements:undefined},id,id,id));
 assert.ok(!validReport({...r,confirmed_requirements:[r.confirmed_requirements[0],r.confirmed_requirements[0]]},id,id,id));
 for(const patch of [{description:''},{description:'x'.repeat(501)},{category:'personality'},{criterion_id:'<script>'},{is_hard:'yes'}]){
  assert.ok(!validReport({...r,confirmed_requirements:[{...r.confirmed_requirements[0],...patch}]},id,id,id));
 }
});
test('screen, print and comparison share the same evidence profile and pending-judgment notice',()=>{
 const r=withRequirements(complete());
 const screen=renderToStaticMarkup(h(AssessmentView,{report:r}));
 const print=renderToStaticMarkup(h(AssessmentView,{report:r,preparedAt:'2026-10-17T12:00:00Z'}));
 const comparison=renderToStaticMarkup(h(ComparisonView,{comparison:{version:'f6-comparison-1',job_id:id,criteria_revision:2,
  reports:[r,structuredClone(r)],review_required:true,notice:'No automatic ranking.'}}));
 for(const html of [screen,print,comparison])for(const text of ['Overall suitability position: pending recruiter confirmation.',
  'Python programming','SQL transactions','Recorded F5 dimension findings','Verify examples.'])assert.ok(html.includes(text),text);
 assert.equal((comparison.match(/aria-label="Suitability evidence profile"/g)??[]).length,2);
 assert.doesNotMatch(print,/<button|<input|<nav/);
});
