import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {SavedInterviews} from '../src/components/InterviewScheduling.ts';
import {storageConfig,prepareStorage,storageDecision,privacyStatus,withdrawStorage,reviewTranscript,isTranscriptReview} from '../src/api/transcripts.ts';
const id='11111111-1111-4111-8111-111111111111';

test('historical interviews retain transcript/privacy navigation without implying current join authorization',()=>{
  const html=renderToStaticMarkup(createElement(SavedInterviews,{rows:[{id,job_id:id,job_reference:'TT-JOB-AAAAAAAAAAAAAAAA',batch_id:id,upload_id:id,
    criteria_revision:2,scoring_version:'f2-coverage-v1',scheduled_at:'2026-10-01T00:00:00Z',timezone:'Asia/Dhaka',duration_minutes:60,unscored_confirmed:false,status:'scheduled'}],
    criteriaRevision:3,onOpenInterview:()=>{throw Error('Rendering must not navigate');}}));
  assert.match(html,/Review transcript \/ privacy/);assert.doesNotMatch(html,/Open interview/);
});

test('separate consent/withdrawal requests are explicit, protected and never retried',async t=>{
  const original=globalThis.fetch; t.after(()=>{globalThis.fetch=original;});const calls:any[]=[];
  globalThis.fetch=async(input,init)=>{calls.push({url:String(input),...init});
    const body=String(input).endsWith('/config')?{enabled:true,version:'optional-transcript-storage-v1',wording:'Synthetic disclosure'}
      :String(input).endsWith('/prepare')?{capture_id:id,interview_id:id,status:'awaiting_consent'}
      :String(input).endsWith('/status')?{withdrawn:false,expired:false,deletion_verified:false,deletion_status:'none'}:{};
    return new Response(JSON.stringify(body),{status:200});};
  const context={candidate:true};
  await storageConfig();const setup=await prepareStorage(context);
  await storageDecision(context,setup.capture_id,'accept');await privacyStatus(context);await withdrawStorage(context);
  assert.equal(calls.filter(c=>c.method==='POST').length,3);
  const accept=calls.find(c=>c.url.endsWith('/decision'));
  assert.equal(accept.headers['X-TalentTrace-Storage-Consent'],'optional-transcript-storage-v1');
  assert.equal(accept.headers['X-TalentTrace-Request'],'1');assert.equal(accept.credentials,'include');
  assert.deepEqual(JSON.parse(accept.body),{capture_id:id,decision:'accept'});
  await assert.rejects(()=>reviewTranscript(context),/recruiter-only/);
  globalThis.fetch=async()=>{calls.push('failed');throw Error('private provider response');};
  await assert.rejects(()=>withdrawStorage(context));assert.equal(calls.filter(c=>c==='failed').length,1);
});

test('review validation rejects fabricated roles, unsafe text and unbounded turns',()=>{
  const value={turns:[{id,capture_id:id,sequence:1,role:'candidate',text:'Synthetic speech.',start_ms:0,end_ms:100}],
    captures:[{id,status:'completed',outcome:'saved',summary:null}],warning:'Chunk estimates only',next_offset:null};
  assert.ok(isTranscriptReview(value));
  for(const patch of [{role:'admin'},{text:'unsafe\x00'},{end_ms:-1},{text:'x'.repeat(1001)}])
    assert.equal(isTranscriptReview({...value,turns:[{...value.turns[0],...patch}]}),false);
  assert.equal(isTranscriptReview({...value,turns:Array(201).fill(value.turns[0])}),false);
});

test('production consent panel starts unchecked and does not treat authorization as saved text',async()=>{
  let index=0;const states:any[]=[],effects:any[]=[],calls:any[]=[];
  const hooks={useState(initial:any){const n=index++;if(!(n in states))states[n]=initial;return [states[n],(v:any)=>{states[n]=v;}];},useEffect(fn:any){effects.push(fn);}};
  const fake={storageConfig:async()=>({enabled:true,version:'optional-transcript-storage-v1',wording:'Approved synthetic disclosure: no more than 30 days.'}),
    prepareStorage:async()=>({capture_id:id,interview_id:id,status:'awaiting_consent'}),
    storageDecision:async(...args:any[])=>{calls.push(args);},privacyStatus:async()=>({withdrawn:false,expired:false,deletion_verified:false,deletion_status:'none',capture_status:'active',persistence_outcome:'pending'}),
    withdrawStorage:async()=>{calls.push('withdraw');},reviewTranscript:async()=>{throw Error('Candidate must not review');}};
  const source=ts.transpileModule(readFileSync(new URL('../src/components/TranscriptPanel.tsx',import.meta.url),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const exports:any={},require=createRequire(import.meta.url);
  runInNewContext(source,{exports,require:(name:string)=>name==='react'?hooks:name==='../api/transcripts'?fake:require(name),setInterval:()=>1,clearInterval(){}});
  function render(){index=0;return exports.default({candidate:true,connected:true});}
  function nodes(n:any):any[]{return !n || typeof n!=='object'?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];}
  const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
  render();effects[0]();await tick();let tree=render();
  nodes(tree).find(n=>n.type==='button'&&n.props.children==='Review optional storage consent').props.onClick();await tick();tree=render();
  let accept=nodes(tree).find(n=>n.type==='button'&&n.props.children==='Accept transcript storage');
  assert.equal(accept.props.disabled,true);assert.equal(calls.length,0);
  nodes(tree).find(n=>n.type==='input').props.onChange({target:{checked:true}});tree=render();
  nodes(tree).find(n=>n.type==='button'&&n.props.children==='Accept transcript storage').props.onClick();await tick();
  assert.equal(calls.length,1);tree=render();
  assert.ok(nodes(tree).some(n=>n.type==='p'&&String(n.props.children).includes('Authorization alone does not mean text was saved')));
  assert.equal(nodes(tree).some(n=>n.type==='button'&&n.props.children==='Load saved transcript'),false);
});
