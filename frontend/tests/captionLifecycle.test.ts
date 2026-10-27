import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {runInNewContext} from "node:vm";
import ts from "typescript";
import {isCaption,isFinalization} from "../src/api/captions.ts";

// Exercise production handlers with controlled hooks/browser APIs, no media/network.
function harness(options:{pendingModule?:boolean;pendingResume?:boolean;suspended?:boolean;cloud?:boolean;recruiter?:boolean;liveCloud?:boolean;generatedMedia?:boolean}={}) {
  const states:any[]=[],refs:any[]=[],effects:any[]=[],sockets:any[]=[],audios:any[]=[],worklets:any[]=[],timers=new Map<number,{callback:()=>void;ms:number}>();
  const finalizerRef:{current:(()=>Promise<void>)|null}={current:null};let timerId=100;
  let stateIndex=0,refIndex=0,finishModule=()=>{},finishResume=()=>{};
  const moduleReady=options.pendingModule?new Promise<void>(r=>{finishModule=r;}):Promise.resolve();
  const resumeReady=options.pendingResume?new Promise<void>(r=>{finishResume=r;}):Promise.resolve();
  const track={readyState:"live",enabled:true,listeners:new Set<()=>void>(),
    addEventListener:(_n:string,f:()=>void)=>track.listeners.add(f),removeEventListener:(_n:string,f:()=>void)=>track.listeners.delete(f)};
  class Audio {
    state="suspended";sampleRate=16000;listeners=new Set<()=>void>();audioWorklet={addModule:()=>moduleReady};destination={};
    constructor(){audios.push(this);}
    addEventListener(_n:string,f:()=>void){this.listeners.add(f);}
    removeEventListener(_n:string,f:()=>void){this.listeners.delete(f);}
    emit(){for(const f of [...this.listeners])f();}
    async close(){this.state="closed";this.emit();}
    async resume(){await resumeReady;if(!options.suspended){this.state="running";this.emit();}}
    createMediaStreamSource(){return {connect(){}};}
    createGain(){return {gain:{value:1},connect(){}};}
  }
  class Socket {
    static OPEN=1;readyState=1;bufferedAmount=0;sent:any[]=[];
    constructor(){sockets.push(this);}
    send(v:any){this.sent.push(v);}
    close(){this.readyState=3;}
  }
  const hooks={useState(initial:any){const i=stateIndex++;if(!(i in states))states[i]=initial;return [states[i],(v:any)=>{states[i]=typeof v==="function"?v(states[i]):v;}];},
    useRef(initial:any){const i=refIndex++;return refs[i]??(refs[i]={current:initial});},useEffect(effect:any){effects.push(effect);}};
  const compiled=ts.transpileModule(readFileSync(new URL("../src/components/InterviewCaptions.tsx",import.meta.url),"utf8"),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText
    .replaceAll("import.meta.url",JSON.stringify(new URL("../src/components/InterviewCaptions.tsx",import.meta.url).href));
  const exports:any={},require=createRequire(import.meta.url);
  runInNewContext(compiled,{exports,require:(n:string)=>n==="react"?hooks:n==="../api/captions"?{captionUrl:()=>"ws://synthetic.test",isCaption,isFinalization}:require(n),
    URL,AudioContext:Audio,MediaStream:class{},AudioWorkletNode:class{port:any={onmessage:null,sent:[],postMessage(v:any){this.sent.push(v);}};constructor(){worklets.push(this);}connect(){}},WebSocket:Socket,
    setTimeout:(callback:()=>void,ms:number)=>{const id=++timerId;timers.set(id,{callback,ms});return id;},clearTimeout:(id:number)=>timers.delete(id),setInterval:()=>2,clearInterval(){}});
  let microphoneMuted=false;
  function render(){stateIndex=0;refIndex=0;return exports.default({connected:true,candidate:!options.recruiter,microphone:()=>track,microphoneMuted,finalizerRef,generatedMedia:options.generatedMedia??true});}
  function find(node:any,p:(n:any)=>boolean):any {
    if(!node || typeof node!=="object")return null;if(p(node))return node;
    for(const child of [node.props?.children].flat(Infinity)){const found=find(child,p);if(found)return found;}return null;
  }
  render();states[3]=options.cloud??false;states[7]=options.liveCloud??false;const cleanup=effects[0]();
  function consent(){let tree=render();find(tree,n=>n.type==="input").props.onChange({target:{checked:true}});tree=render();
    find(tree,n=>n.type==="button" && n.props.children==="Consent to captions").props.onClick();const ws=sockets.at(-1);ws.onopen();return ws;}
  async function flush(){for(let i=0;i<12;i++)await Promise.resolve();}
  return {states,track,audios,worklets,render,find,setMuted:(v:boolean)=>{microphoneMuted=v;return render();},cleanup,consent,flush,event:(ws:any,v:any)=>ws.onmessage({data:JSON.stringify(v)}),finishModule:()=>finishModule(),finishResume:()=>finishResume(),finish:()=>finalizerRef.current!(),timeout:(ms:number)=>{const t=[...timers.values()].find(t=>t.ms===ms);assert.ok(t);t.callback();}};
}

test("Live status requires running AudioContext; unexpected closure ends captions without stopping microphone",async()=>{
  const h=harness({pendingResume:true}),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
  assert.equal(h.states[1],"Starting caption audio capture…");h.finishResume();await h.flush();assert.match(h.states[1],/^Live/);
  await h.audios[0].close();await h.flush();assert.match(h.states[1],/audio capture ended/);
  assert.equal(ws.readyState,3);assert.equal(h.track.readyState,"live");assert.equal(h.track.enabled,true);
  assert.equal(h.audios[0].listeners.size,0);assert.equal(h.track.listeners.size,0);
});

test("cleanup during worklet setup suppresses late Live status and removes listeners",async()=>{
  const h=harness({pendingModule:true}),ws=h.consent();h.event(ws,{kind:"active"});h.cleanup();h.finishModule();await h.flush();
  assert.match(h.states[1],/Captions stopped/);assert.equal(ws.readyState,3);assert.equal(h.audios[0].state,"closed");
  assert.equal(h.track.listeners.size,0);assert.equal(h.track.enabled,true);
});

test("server stop clears captions and intentional context closure is not reported as a capture failure",async()=>{
  const h=harness(),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
  h.event(ws,{kind:"caption",role:"candidate",sequence:1,start:0,end:2,text:"Synthetic caption"});assert.equal(h.states[2].length,1);
  h.event(ws,{kind:"stopped"});await h.flush();assert.equal(h.states[2].length,0);assert.match(h.states[1],/Captions stopped/);
  assert.equal(h.audios[0].state,"closed");assert.equal(h.track.readyState,"live");
});

test("non-running context never reports Live; ended microphone stops caption processing",async()=>{
  const failed=harness({suspended:true}),ws=failed.consent();failed.event(ws,{kind:"active"});await failed.flush();
  assert.match(failed.states[1],/unavailable/);assert.equal(ws.readyState,3);
  const h=harness(),live=h.consent();h.event(live,{kind:"active"});await h.flush();
  h.track.readyState="ended";for(const listener of [...h.track.listeners])listener();await h.flush();
  assert.match(h.states[1],/audio capture ended/);assert.equal(live.readyState,3);
});


test("interview mute stops separate STT forwarding and unmute resumes without new consent",async()=>{
  const h=harness(),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
  const send=()=>h.worklets[0].port.onmessage({data:new ArrayBuffer(3200)});
  send();assert.equal(ws.sent.length,2); // consent plus one PCM frame
  h.setMuted(true);send();assert.equal(ws.sent.length,2);assert.equal(ws.readyState,1);
  h.setMuted(false);send();assert.equal(ws.sent.length,3);
  h.track.enabled=false;send();assert.equal(ws.sent.length,3);
  h.track.enabled=true;h.track.muted=true;send();assert.equal(ws.sent.length,3);
  h.cleanup();send();assert.equal(ws.sent.filter((v:any)=>typeof v!=="string").length,2);
});

test("five-minute test uses server bounds and cleanup preserves the interview track",async()=>{
  const h=harness(),ws=h.consent();h.event(ws,{kind:"active",duration_seconds:300});await h.flush();
  assert.match(h.states[1],/300 seconds/);
  h.event(ws,{kind:"caption",role:"candidate",sequence:150,start:296,end:300,text:"Synthetic tail"});
  assert.equal(h.states[2].length,1);
  h.event(ws,{kind:"stopped"});await h.flush();assert.equal(h.states[2].length,0);
  assert.equal(h.track.readyState,"live");assert.equal(h.audios[0].state,"closed");
  const bad=harness(),other=bad.consent();bad.event(other,{kind:"active",duration_seconds:301});await bad.flush();
  assert.equal(other.readyState,3);assert.equal(bad.audios.length,0);
});

test("normal finish flushes residual PCM, waits for ACK and terminal result before closing",async()=>{
  const h=harness(),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
  h.worklets[0].port.onmessage({data:new ArrayBuffer(3200)});
  let resolved=false;const pending=h.finish().then(()=>{resolved=true;});
  assert.equal(ws.sent.at(-1),"finish");assert.equal(ws.readyState,1);
  h.event(ws,{kind:"finishing",deadline_seconds:35});
  assert.equal(h.worklets[0].port.sent.at(-1).kind,"flush");
  h.worklets[0].port.onmessage({data:new ArrayBuffer(100)});
  h.worklets[0].port.onmessage({data:{kind:"flushed",captured_samples:1650}});
  assert.deepEqual(JSON.parse(ws.sent.at(-1)),{kind:"end",frames:2,samples:1650,captured_samples:1650});
  assert.equal(h.audios[0].state,"closed");assert.equal(ws.readyState,1);assert.equal(resolved,false);
  h.event(ws,{kind:"accepted",frames:2,samples:1650});
  h.event(ws,{kind:"caption",role:"candidate",sequence:1,start:0,end:.11,text:"Synthetic tail"});
  assert.equal(h.states[2].length,1);
  const empty={accepted_frames:0,accepted_samples:0,processed_samples:0,caption_events:0,captured_samples:0};
  h.event(ws,{kind:"finalized",outcome:"drained",roles:{recruiter:empty,candidate:{accepted_frames:2,accepted_samples:1650,processed_samples:1650,caption_events:1,captured_samples:1650}}});
  assert.equal(ws.readyState,1);assert.equal(resolved,false);
  h.event(ws,{kind:"stopped"});
  await pending;assert.equal(resolved,true);assert.equal(ws.readyState,3);
  assert.match(h.states[1],/Finalization: drained/);assert.equal(h.states[2].length,0);
  assert.equal(h.track.readyState,"live");assert.equal(h.track.enabled,true);
});

test("duplicate normal finish shares one request and withdrawal aborts instead of flushing",async()=>{
  const h=harness(),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
  const a=h.finish(),b=h.finish();assert.equal(a,b);assert.equal(ws.sent.filter((s:any)=>s==="finish").length,1);
  h.cleanup();await a;assert.equal(ws.sent.at(-1),"stop");
  assert.ok(!h.worklets[0].port.sent.some((v:any)=>v.kind==="flush"));
});

test("missing worklet flush and uncertain server response are bounded without retry",async()=>{
  for(const timeout of [2000,40000]){
    const h=harness(),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
    const pending=h.finish();h.event(ws,{kind:"finishing",deadline_seconds:35});
    h.timeout(timeout);await pending;
    assert.equal(ws.readyState,3);assert.match(h.states[1],/incomplete|unconfirmed/);
    assert.equal(ws.sent.filter((v:any)=>v==="finish").length,1);
  }
});

test("network interruption while finishing resolves leave and stops capture",async()=>{
  const h=harness(),ws=h.consent();h.event(ws,{kind:"active"});await h.flush();
  const pending=h.finish();h.event(ws,{kind:"finishing",deadline_seconds:35});ws.onclose();await pending;
  assert.equal(h.audios[0].state,"closed");assert.equal(h.track.readyState,"live");
  assert.ok(!h.states[1].includes("drained"));
});


test("synthetic cloud mode never captures microphone and requires recruiter replay action",async()=>{
  const h=harness({cloud:true,recruiter:true}),ws=h.consent();
  h.event(ws,{kind:"active",duration_seconds:120,source:"assemblyai-synthetic"});await h.flush();
  assert.equal(h.audios.length,0);assert.equal(h.worklets.length,0);
  assert.ok(ws.sent.every((v:any)=>typeof v==="string"));
  assert.ok(!ws.sent.includes("synthetic-start"));
  let tree=h.render();h.find(tree,(n:any)=>n.type==="button"&&n.props.children==="Start fixed synthetic cloud replay").props.onClick();
  assert.equal(ws.sent.at(-1),"synthetic-start");
  h.event(ws,{kind:"synthetic-complete"});assert.match(h.states[1],/provider streams terminated/);
  h.cleanup();assert.equal(ws.readyState,3);
});

test("candidate has no replay control and mode mismatch fails closed",async()=>{
  const h=harness({cloud:true});assert.equal(h.find(h.render(),(n:any)=>n.type==="button"&&n.props.children==="Start fixed synthetic cloud replay"),null);
  const ws=h.consent();h.event(ws,{kind:"active"});assert.equal(ws.readyState,3);assert.equal(h.audios.length,0);
  const local=harness(),other=local.consent();local.event(other,{kind:"active",source:"assemblyai-synthetic"});
  assert.equal(other.readyState,3);assert.equal(local.audios.length,0);
});

test('live cloud uses the existing AudioWorklet after independent consent, without F11 replay',async()=>{
  const h=harness({liveCloud:true}),ws=h.consent();
  h.event(ws,{kind:'active',duration_seconds:120,source:'assemblyai-live'});await h.flush();
  assert.equal(h.audios.length,1);assert.equal(h.worklets.length,1);
  assert.match(h.states[1],/AssemblyAI/);
  assert.equal(h.find(h.render(),(n:any)=>n.type==='button'&&n.props.children==='Start fixed synthetic cloud replay'),null);
  h.event(ws,{kind:'provider-termination',confirmed:false,sessions:2});h.event(ws,{kind:'stopped'});
  assert.match(h.states[1],/termination unconfirmed/);
});

test('live mode rejects physical-media selection and local/live source mismatch',()=>{
  const physical=harness({liveCloud:true,generatedMedia:false});
  const button=physical.find(physical.render(),(n:any)=>n.type==='button'&&n.props.children==='Consent to captions');
  assert.equal(button.props.disabled,true);
  const live=harness({liveCloud:true}),ws=live.consent();live.event(ws,{kind:'active'});
  assert.equal(ws.readyState,3);assert.equal(live.audios.length,0);
});
