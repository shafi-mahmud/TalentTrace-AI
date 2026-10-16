import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {startAnalysis,analysisStatus,analysisConfig,isAnalysisOperation} from '../src/api/interviewAnalysis.ts';
const id='12345678-1234-4234-8234-123456789012';
test('navigation and polling do not POST, explicit analysis retains mutation and disclosure protection',async()=>{
  const calls:any[]=[];
  globalThis.fetch=async(url:any,options:any)=>{calls.push({url,...options});return new Response(JSON.stringify(String(url).endsWith('/config')?
    {enabled:true,version:'synthetic-interview-analysis-v1',disclosure:'Synthetic only'}:
    {operation_id:id,status:'running',error:null,persistence:'ephemeral_single_worker',result:null}),{status:200});};
  await analysisConfig();await startAnalysis(id,id,2,id);await analysisStatus(id,id,id);
  assert.equal(calls.filter(v=>v.method==='POST').length,1);
  const post=calls.find(v=>v.method==='POST');
  assert.equal(post.headers['X-TalentTrace-Job-Revision'],'2');
  assert.equal(post.headers['X-TalentTrace-Evaluation-Disclosure'],'synthetic-interview-analysis-v1');
  assert.equal(post.credentials,'include');assert.equal(post.cache,'no-store');
  let failed=0;globalThis.fetch=async()=>{failed++;throw Error('private provider text');};
  await assert.rejects(()=>startAnalysis(id,id,2,id));assert.equal(failed,1);
});
test('incomplete and failed operations cannot masquerade as model results',()=>{
  const v={operation_id:id,status:'failed',error:'processing_failed',persistence:'ephemeral_single_worker',result:null};
  assert.ok(isAnalysisOperation(v));assert.equal(isAnalysisOperation({...v,result:{mock:'fabricated'}}),false);
  assert.equal(isAnalysisOperation({...v,status:'completed',result:{provider:'mock'}}),false);
});
test('UI has no automatic model launch and labels evidence, interpretation and ephemeral state',()=>{
  const text=readFileSync(new URL('../src/components/InterviewAnalysis.tsx',import.meta.url),'utf8');
  assert.ok(text.includes('AI interpretation — recruiter review required.'));
  assert.ok(text.includes('Transcript evidence:'));assert.ok(text.includes('No overall score or hire/reject recommendation'));
  assert.ok(text.includes('setId(next)'));assert.ok(text.includes('crypto.randomUUID()'));
  assert.ok(text.includes('Displayed results cleared'));assert.ok(!text.includes('localStorage'));
  assert.ok(text.includes('checked={checked}'));assert.ok(text.includes('status===\'completed\''));
});
