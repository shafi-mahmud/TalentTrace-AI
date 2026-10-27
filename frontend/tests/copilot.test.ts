import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import * as api from '../src/api/copilot.ts';
const id='11111111-1111-4111-8111-111111111111';
const context={candidate:false,jobId:id,interviewId:id};
const suggestion={id:'a'.repeat(64),question:'Could you give a Python example?',requirement:'Python',
  reason:'Linked provisional context; not an assessment.',provisional:true};
const view=()=>({enabled:true,live_connected:false,version:api.version,wording:'Separate temporary local assistant disclosure.',
  status:'authorized',run_id:id,epoch:1,recruiter_consented:true,candidate_consented:true,expires_in_ms:100000,suggestion,processing:'suggested'});

test('separate explicit consent, cookie path, no-store requests and no public ingestion',async t=>{
  const original=globalThis.fetch;t.after(()=>{globalThis.fetch=original;});const calls:any[]=[];
  globalThis.fetch=async(input,init)=>{
    calls.push({url:String(input),...init});const v:any=view();
    if(String(input).includes('/interview-access/')){delete v.suggestion;delete v.processing;}
    return new Response(JSON.stringify(v),{status:200});};
  await api.status(context);await api.prepare(context);await api.decide(context,view() as api.Status,'accept');
  await api.decide({candidate:true},view() as api.Status,'withdraw');await api.dismiss(context,view() as api.Status);
  for(const call of calls){assert.equal(call.cache,'no-store');assert.equal(call.credentials,'include');
    assert.equal(call.headers['X-TalentTrace-Request'],'1');assert.ok(call.signal);}
  assert.equal(calls[0].method,'GET');assert.equal(calls[0].body,undefined);
  assert.match(calls[3].url,/api\/v1\/interview-access\/copilot\/consent$/);
  assert.deepEqual(JSON.parse(calls[2].body),{run_id:id,epoch:1,version:api.version,decision:'accept'});
  assert.equal(calls.some(c=>/events|transcript|speech/.test(c.url)),false);
  await assert.rejects(()=>api.prepare({candidate:true}),/Recruiter only/);
  await assert.rejects(()=>api.dismiss({candidate:true},view() as api.Status),/Recruiter/);
});

test('transport errors never expose provider details or automatically retry',async t=>{
  const original=globalThis.fetch;t.after(()=>{globalThis.fetch=original;});let calls=0;
  globalThis.fetch=async()=>{calls++;return new Response('private sentinel',{status:409});};
  await assert.rejects(()=>api.decide(context,view() as api.Status,'accept'),e=>e instanceof Error&&!e.message.includes('sentinel'));
  assert.equal(calls,1);
});

test('assistant configuration rejects malformed or conflicting cloud source flags',async t=>{
  const original=globalThis.fetch;t.after(()=>{globalThis.fetch=original;});
  const base={enabled:true,live_connected:false,version:api.version,wording:'Separate consent.'};
  for(const patch of [{live_cloud:'true'},{synthetic_cloud:true,live_cloud:true}]){
    globalThis.fetch=async()=>new Response(JSON.stringify({...base,...patch}),{status:200});
    await assert.rejects(()=>api.config(),/configuration unavailable/);
  }
  globalThis.fetch=async()=>new Response(JSON.stringify({...base,synthetic_cloud:false,live_cloud:true}),{status:200});
  assert.equal((await api.config()).live_cloud,true);
});

test('candidate rejects suggestion/coverage payloads and recruiter rejects unsafe output',()=>{
  assert.equal(api.validStatus(view(),false),true);assert.equal(api.validStatus(view(),true),false);
  const {suggestion:_,processing:__,...candidate}=view();
  assert.equal(api.validStatus(candidate,true),true);
  assert.equal(api.validStatus({...candidate,exploration:[]},true),false);
  for(const patch of [{status:'withdrawn'},{candidate_consented:false},{suggestion:{...suggestion,question:'x\x00'}},
    {suggestion:{...suggestion,provisional:false}},{expires_in_ms:120001},{live_connected:'invalid'}])
    assert.equal(api.validStatus({...view(),...patch},false),false);
});

test('response fences block stale polls after withdrawal, leave and replacement',()=>{
  const fence=new api.ResponseFence();const old=fence.next();fence.clear();assert.equal(fence.accepts(old),false);
  const current=fence.next();assert.equal(fence.accepts(current),true);fence.next();assert.equal(fence.accepts(current),false);
});

function harness(candidate=false,cloud=false,liveCloud=false){
  let index=0;const slots:any[]=[];const effects:any[]=[];const intervals=new Map<number,()=>void>();
  const timers=new Map<number,()=>void>();let timer=0;let now=0;const calls:any[]=[];const due=new Map<number,number>();const intervalDue=new Map<number,{next:number;period:number}>();
  let nextStatus:()=>Promise<any>=async()=>{const v:any=view();if(candidate){delete v.suggestion;delete v.processing;}return v;};
  let nextPrepare=async()=>({...view(),status:'awaiting_consent',suggestion:null,recruiter_consented:false,candidate_consented:false});
  const hooks={
    useState(initial:any){const n=index++;if(!(n in slots))slots[n]=initial;return [slots[n],(v:any)=>{slots[n]=typeof v==='function'?v(slots[n]):v;}];},
    useRef(initial:any){const n=index++;if(!(n in slots))slots[n]={current:initial};return slots[n];},
    useEffect(fn:any,deps:any[]){const n=index++;const before=slots[n];if(!before||deps.some((v,i)=>v!==before.deps[i])){
      slots[n]={deps,cleanup:before?.cleanup};effects.push(()=>{slots[n].cleanup?.();slots[n].cleanup=fn();});}}
  };
  const fake={ResponseFence:api.ResponseFence,
    config:async()=>({enabled:true,live_connected:false,version:api.version,wording:cloud?'AssemblyAI receives only fixed synthetic eSpeak audio; model-training use is possible.':'Independent temporary processing disclosure.',synthetic_cloud:cloud,live_cloud:liveCloud,live_enabled:true}),
    status:async()=>{calls.push('status');const v=await nextStatus();if(!api.validStatus(v,candidate))throw Error('Invalid status');return v;},
    prepare:async()=>{calls.push('prepare');return nextPrepare();},
    decide:async(_c:any,_s:any,decision:string)=>{calls.push(decision);return {...view(),status:decision==='accept'?'authorized':'withdrawn',epoch:2,suggestion:null};},
    dismiss:async()=>{calls.push('dismiss');return {...view(),suggestion:null};}};
  const source=ts.transpileModule(readFileSync(new URL('../src/components/InterviewCopilot.tsx',import.meta.url),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const exports:any={},require=createRequire(import.meta.url);
  const window={setInterval(fn:()=>void,ms:number){intervals.set(++timer,fn);intervalDue.set(timer,{next:now+ms,period:ms});return timer;},clearInterval(n:number){intervals.delete(n);intervalDue.delete(n);},
    setTimeout(fn:()=>void,ms:number){timers.set(++timer,fn);due.set(timer,now+ms);return timer;},clearTimeout(n:number){timers.delete(n);due.delete(n);}};
  runInNewContext(source,{exports,require:(name:string)=>name==='react'?hooks:name==='../api/copilot'?fake:require(name),window});
  let connected=true;
  const render=()=>{index=0;const tree=exports.default({...context,candidate,connected});while(effects.length)effects.shift()();return tree;};
  const tick=async()=>{for(let n=0;n<30;n++)await Promise.resolve();};
  const settle=async()=>{render();await tick();render();await tick();return render();};
  const advance=async(ms:number)=>{
    now+=ms;
    for(const [id,schedule] of intervalDue)while(schedule.next<=now&&intervals.has(id)){
      schedule.next+=schedule.period;intervals.get(id)!();await tick();render();
    }
    for(const [id,deadline] of [...due])if(deadline<=now&&timers.has(id)){
      const fn=timers.get(id)!;timers.delete(id);due.delete(id);fn();await tick();render();
    }
    return render();
  };
  return {render,settle,tick,advance,now:()=>now,calls,intervals,timers,setPrepare(fn:()=>Promise<any>){nextPrepare=fn;},setStatus(fn:()=>Promise<any>){nextStatus=fn;},disconnect(){connected=false;}};
}
function nodes(n:any):any[]{return !n||typeof n!=='object'?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];}
function button(tree:any,label:string){return nodes(tree).find(n=>n.type==='button'&&n.props.children===label);}

test('candidate panel exposes only consent controls; no suggestion or requirement display',async()=>{
  const h=harness(true);const tree=await h.settle();
  assert.equal(nodes(tree).some(n=>n.props?.['aria-label']==='Provisional question suggestion'),false);
  assert.equal(button(tree,'Dismiss / Ignore'),undefined);assert.equal(button(tree,'Prepare new assistant run'),undefined);
  assert.ok(button(tree,'Withdraw assistant consent'));assert.equal(h.calls.filter(c=>c==='accept').length,0);
});

test('checkbox starts unchecked; prepare does not opt in; accept and withdraw explicit once',async()=>{
  const h=harness();let tree=await h.settle();button(tree,'Prepare new assistant run').props.onClick();await h.tick();tree=h.render();
  assert.equal(h.calls.filter(c=>c==='prepare').length,1);
  assert.equal(button(tree,'Agree to assistant processing').props.disabled,true);
  assert.equal(h.calls.includes('accept'),false);
  nodes(tree).find(n=>n.type==='input').props.onChange({target:{checked:true}});tree=h.render();
  button(tree,'Agree to assistant processing').props.onClick();await h.tick();tree=h.render();
  assert.equal(h.calls.filter(c=>c==='accept').length,1);
  button(tree,'Withdraw assistant consent').props.onClick();await h.tick();tree=h.render();
  assert.equal(h.calls.filter(c=>c==='withdraw').length,1);
  assert.equal(nodes(tree).some(n=>n.props?.['aria-label']==='Provisional question suggestion'),false);
});

test('disconnect invalidates an in-flight authorized poll so it cannot restore suggestions',async()=>{
  const h=harness();await h.settle();let resolve!:(v:any)=>void;
  h.setStatus(()=>new Promise(r=>{resolve=r;}));for(const fn of h.intervals.values())fn();await h.tick();
  h.disconnect();h.render();resolve(view());await h.tick();const tree=h.render();
  assert.equal(nodes(tree).some(n=>n.props?.['aria-label']==='Provisional question suggestion'),false);
  assert.ok(h.calls.includes('withdraw'));
});

test('suggestion local expiry clears display and does not repeat a mutation',async()=>{
  const h=harness();let tree=await h.settle();assert.ok(button(tree,'Dismiss / Ignore'));
  for(const fn of [...h.timers.values()])fn();tree=h.render();
  assert.equal(button(tree,'Dismiss / Ignore'),undefined);
  assert.equal(h.calls.filter(c=>c==='accept').length,0);
});

test('no browser persistence or caption broadcast channel is used',()=>{
  const source=readFileSync(new URL('../src/components/InterviewCopilot.tsx',import.meta.url),'utf8');
  assert.doesNotMatch(source,/localStorage|indexedDB|sessionStorage|WebSocket/);
  const live=readFileSync(new URL('../src/components/LiveInterviewPage.tsx',import.meta.url),'utf8');
  assert.match(live,/<InterviewCopilot/);
});


test('withdrawal can interrupt a slow poll and late response cannot restore suggestion',async()=>{
  const h=harness();let tree=await h.settle();let resolve!:(v:any)=>void;
  h.setStatus(()=>new Promise(r=>{resolve=r;}));for(const fn of h.intervals.values())fn();await h.tick();
  tree=h.render();button(tree,'Withdraw assistant consent').props.onClick();await h.tick();tree=h.render();
  assert.equal(h.calls.filter(c=>c==='withdraw').length,1);
  resolve(view());await h.tick();tree=h.render();
  assert.equal(button(tree,'Dismiss / Ignore'),undefined);
  assert.ok(nodes(tree).some(n=>n.props?.role==='status'&&String(n.props.children).includes('withdrawn')));
});


test('live adapter status is supported without implying technical assessment',()=>{
  assert.equal(api.validStatus({...view(),live_connected:true},false),true);
  const {suggestion:_,processing:__,...candidate}=view();
  assert.equal(api.validStatus({...candidate,live_connected:true},true),true);
});


const hasQuestion=(tree:any)=>nodes(tree).some(n=>n.props?.['aria-label']==='Provisional question suggestion');

test('validated positive poll displays through eight samples of a 15-second result window',async()=>{
  const h=harness();
  h.setStatus(async()=>({...view(),expires_in_ms:120000-h.now(),suggestion:h.now()>=4000&&h.now()<19000?suggestion:null}));
  assert.equal(hasQuestion(await h.settle()),false);
  await h.advance(2000);assert.equal(hasQuestion(h.render()),false);
  for(let sample=0;sample<8;sample++){
    const tree=await h.advance(2000);assert.equal(hasQuestion(tree),true);
    assert.ok(nodes(tree).some(n=>n.type==='p'&&n.props.children===suggestion.question));
  }
  assert.equal(hasQuestion(await h.advance(2000)),false);
  assert.equal(h.calls.filter(c=>c==='prepare').length,0);
  assert.equal(h.calls.filter(c=>c==='accept').length,0);
});

test('competing manual refresh and interval ticks do not race a pending status response',async()=>{
  const h=harness();await h.settle();let resolve!:(v:any)=>void;
  h.setStatus(()=>new Promise(r=>{resolve=r;}));const before=h.calls.filter(c=>c==='status').length;
  for(const fn of h.intervals.values())fn();await h.tick();
  button(h.render(),'Check assistant status').props.onClick();
  for(const fn of h.intervals.values())fn();await h.tick();
  assert.equal(h.calls.filter(c=>c==='status').length,before+1);
  resolve(view());await h.tick();assert.equal(hasQuestion(h.render()),true);
});

test('failed prepare does not prevent a later successful validated suggestion poll',async()=>{
  const h=harness();await h.settle();h.setPrepare(async()=>{throw Error('409');});
  button(h.render(),'Prepare new assistant run').props.onClick();await h.tick();
  assert.equal(hasQuestion(h.render()),false);
  for(const fn of h.intervals.values())fn();await h.tick();
  assert.equal(hasQuestion(h.render()),true);assert.equal(h.calls.filter(c=>c==='prepare').length,1);
});

test('withdrawal clears the provisional article synchronously before awaiting the server',async()=>{
  const h=harness();await h.settle();assert.equal(hasQuestion(h.render()),true);
  button(h.render(),'Withdraw assistant consent').props.onClick();
  assert.equal(hasQuestion(h.render()),false);
  await h.tick();assert.equal(hasQuestion(h.render()),false);
});

test('cloud mode discloses AssemblyAI and training before consent without local-only claims',async()=>{
  const h=harness(false,true);h.setStatus(async()=>({...view(),recruiter_consented:false,status:'awaiting_consent',suggestion:null}));
  const tree=await h.settle();const words=nodes(tree).flatMap(n=>typeof n.props?.children==='string'?[n.props.children]:[]).join(' ');
  assert.match(words,/AssemblyAI/);assert.match(words,/model-training/);
  assert.doesNotMatch(words,/without sending it to an external|Local F4 adapter enabled/);
  assert.ok(nodes(tree).some(n=>n.type==='label'&&JSON.stringify(n.props.children).includes('separate cloud-caption consent')));
});

test('dismiss interrupts an in-flight poll and stale suggestion cannot reappear',async()=>{
  const h=harness();await h.settle();assert.equal(hasQuestion(h.render()),true);
  let resolve!:(value:any)=>void;
  h.setStatus(()=>new Promise(r=>{resolve=r;}));
  for(const fn of h.intervals.values())fn();await h.tick();
  button(h.render(),'Dismiss / Ignore').props.onClick();
  assert.equal(hasQuestion(h.render()),false);
  await h.tick();assert.equal(h.calls.filter(c=>c==='dismiss').length,1);
  resolve(view());await h.tick();
  assert.equal(hasQuestion(h.render()),false);
  assert.equal(h.calls.filter(c=>c==='withdraw').length,0);
});

test('live cloud assistant accurately labels generated track captions before consent',async()=>{
  const h=harness(false,false,true);h.setStatus(async()=>({...view(),recruiter_consented:false,status:'awaiting_consent',suggestion:null}));
  const tree=await h.settle();const words=nodes(tree).flatMap(n=>typeof n.props?.children==='string'?[n.props.children]:[]).join(' ');
  assert.match(words,/AssemblyAI live captions/);assert.doesNotMatch(words,/Local F4 adapter enabled|fixed synthetic/);
  assert.ok(nodes(tree).some(n=>n.type==='label'&&JSON.stringify(n.props.children).includes('separate cloud-caption consent')));
});
