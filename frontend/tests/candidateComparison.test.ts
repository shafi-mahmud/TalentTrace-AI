import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
import CandidateComparison,{ComparisonView} from '../src/components/CandidateComparison.ts';
import {fetchComparison,validComparison,validSelections,sameApplication} from '../src/api/candidateComparison.ts';
import type {Comparison,ApplicationIdentity} from '../src/api/candidateComparison';
import type {ConsolidatedReport} from '../src/api/consolidatedAssessment';
const job='00000000-0000-4000-8000-000000000001',upload='00000000-0000-4000-8000-000000000002';
const selections:ApplicationIdentity[]=[{job_id:job,batch_id:job,upload_id:job},{job_id:job,batch_id:job,upload_id:upload}];
function report(id:string):ConsolidatedReport{return {
 version:'f6-increment-1',job_id:job,job_title:'Synthetic role',job_reference:'TT-JOB-0000000000000001',batch_id:job,upload_id:id,
 confirmed_requirements:[],criteria_revision:2,cv_source:'current_saved_score',review_required:true,notice:'Recruiter review required. Missing evidence is not poor performance.',
 cv:{job_reference:'TT-JOB-0000000000000001',upload_id:id,screening_decision:'eligible',status:'not_evaluated',reason:'uncertain_evidence',
 weights:{skill:100,experience:0,education:0},score:null,dimensions:[]},
 interview:{state:'not_scheduled',interview_id:null,operation_id:null,rubric_version:null,retention_deadline:null,warning:null,
 pairs:[],requirements:[],assessment:null,references:[],turns:[]}};}
function fixture():Comparison{return {version:'f6-comparison-1',job_id:job,criteria_revision:2,reports:[report(job),report(upload)],
 review_required:true,notice:'No combined score, ranking or hiring recommendation.'};}
function complete(r:ConsolidatedReport){r.interview={state:'available',interview_id:upload,operation_id:upload,rubric_version:'interview-evidence-v1',
 retention_deadline:new Date(Date.now()+60000).toISOString(),warning:'ASR unverified.',
 pairs:[{id:upload,question:'Synthetic question?',answer:'Synthetic answer',question_turns:[job],answer_turns:[upload],capture_id:job,status:'answered',warnings:[],start_ms:0,end_ms:2000}],
 requirements:[{criterion_id:'python',description:'Python',coverage:'partial',explanation:'Topic only.',follow_up:'Verify an example.',qa_ids:[upload],turn_ids:[upload]}],
 assessment:{answers:[{qa_id:upload,dimensions:['relevance','technical_accuracy','completeness','articulation'].map(d=>({dimension:d,status:'uncertain',justification:'Saved synthetic finding.',evidence:[]})),technical_citations:[],follow_up:'Follow up.'}]},
 references:[],turns:[{id:upload,role:'candidate',text:'Synthetic answer',session_id:job,start_ms:1000,end_ms:2000}]};}
test('same-job exact identities required; duplicate rejected, batch identity retained',()=>{
 assert.ok(validSelections(job,selections));assert.ok(!validSelections(job,[selections[0],selections[0]]));
 assert.ok(!validSelections(job,[selections[0],{...selections[1],job_id:upload}]));
 assert.ok(!sameApplication(selections[0],{...selections[0],batch_id:upload}));
});
test('response validation rejects wrong identities/order/revisions/weights and stale protected text',()=>{
 const c=fixture();assert.ok(validComparison(c,job,2,selections));
 assert.ok(!validComparison({...c,reports:[...c.reports].reverse()},job,2,selections));
 assert.ok(!validComparison(c,job,3,selections));
 c.reports[1].cv.weights={skill:50,experience:30,education:20};assert.ok(!validComparison(c,job,2,selections));
 const v=fixture();complete(v.reports[1]);v.reports[1].interview.state='withdrawn';assert.ok(!validComparison(v,job,2,selections));
});
test('CV-only versus authorized interview renders original F5 dimensions, gaps and evidence',()=>{
 const c=fixture();complete(c.reports[1]);assert.ok(validComparison(c,job,2,selections));
 const html=renderToStaticMarkup(h(ComparisonView,{comparison:c}));
 for(const text of ['Application A','Application B','Not scored','No interview is scheduled','Saved synthetic finding','technical_accuracy','Requirement coverage and gaps','Verify an example.','Source'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/0.00 \/ 100|Winner|Recommended candidate/);
});
test('missing/withdrawn/ambiguous states preserve CV context without interview disclosure',()=>{
 for(const state of ['missing_analysis','withdrawn','expired','deleted','ambiguous'] as const){
  const c=fixture();c.reports[1].interview.state=state;
  const html=renderToStaticMarkup(h(ComparisonView,{comparison:c}));assert.match(html,/Application B/);
  assert.doesNotMatch(html,/Saved synthetic finding|Synthetic answer/);
  if(state==='ambiguous')assert.match(html,/Explicit version selection is required/);
 }
});
test('fresh comparison uses one credentialed uncached GET and preserves selection order',async()=>{
 const old=fetch;let calls=0;
 globalThis.fetch=async(url,init)=>{calls++;assert.match(String(url),/assessment-comparison\?/);assert.match(String(url),new RegExp(`right_upload=${upload}`));
 assert.equal(init?.method,undefined);assert.equal(init?.cache,'no-store');assert.equal(init?.credentials,'include');return new Response(JSON.stringify(fixture()));};
 try{assert.deepEqual(await fetchComparison(job,2,selections),fixture());assert.deepEqual(await fetchComparison(job,2,selections),fixture());assert.equal(calls,2);}finally{globalThis.fetch=old;}
});
test('invalid selections never request data; authorization errors never expose private response bodies',async()=>{
 const old=fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;return new Response('private assessment',{status:403});};
 try{await assert.rejects(fetchComparison(job,2,[selections[0],selections[0]]));assert.equal(calls,0);
 await assert.rejects(fetchComparison(job,2,selections),e=>e instanceof Error&&!e.message.includes('private'));assert.equal(calls,1);}finally{globalThis.fetch=old;}
});
test('selectors require explicit choice and comparison; a single saved application has an honest empty state',()=>{
 const html=renderToStaticMarkup(h(CandidateComparison,{jobId:job,revision:2,applications:[]}));
 assert.match(html,/At least two current saved applications/);assert.match(html,/Compare selected applications/);assert.match(html,/disabled/);
 assert.doesNotMatch(html,/Candidate comparison results/);
});
test('responsive columns stack and memory clears on navigation, hiding and retention expiry',()=>{
 const css=readFileSync(new URL('../src/index.css',import.meta.url),'utf8');assert.match(css,/\.comparison-columns \{ display: grid/);
 assert.match(css,/@media\(max-width:1000px\)/);assert.match(css,/\.comparison-columns, \.comparison-selectors \{ grid-template-columns: minmax\(0,1fr\)/);
 const source=readFileSync(new URL('../src/components/CandidateComparison.ts',import.meta.url),'utf8');
 assert.match(source,/visibilitychange/);assert.match(source,/hashchange/);assert.match(source,/retention_deadline/);
 assert.doesNotMatch(source,/localStorage|sessionStorage|window.print/);
});
