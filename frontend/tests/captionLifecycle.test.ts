import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {runInNewContext} from "node:vm";
import ts from "typescript";
import {isCaption} from "../src/api/captions.ts";

// Exercise production handlers with controlled hooks/browser APIs, no media/network.
function harness(options:{pendingModule?:boolean;pendingResume?:boolean;suspended?:boolean}={}) {
  const states:any[]=[],refs:any[]=[],effects:any[]=[],sockets:any[]=[],audios:any[]=[],worklets:any[]=[];
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
  runInNewContext(compiled,{exports,require:(n:string)=>n==="react"?hooks:n==="../api/captions"?{captionUrl:()=>"ws://synthetic.test",isCaption}:require(n),
    URL,AudioContext:Audio,MediaStream:class{},AudioWorkletNode:class{port:any={onmessage:null};constructor(){worklets.push(this);}connect(){}},WebSocket:Socket,
    setTimeout:()=>1,clearTimeout(){},setInterval:()=>2,clearInterval(){}});
  let microphoneMuted=false;
  function render(){stateIndex=0;refIndex=0;return exports.default({connected:true,candidate:true,microphone:()=>track,microphoneMuted});}
  function find(node:any,p:(n:any)=>boolean):any {
    if(!node || typeof node!=="object")return null;if(p(node))return node;
    for(const child of [node.props?.children].flat(Infinity)){const found=find(child,p);if(found)return found;}return null;
  }
  render();const cleanup=effects[0]();
  function consent(){let tree=render();find(tree,n=>n.type==="input").props.onChange({target:{checked:true}});tree=render();
    find(tree,n=>n.type==="button" && n.props.children==="Consent to captions").props.onClick();const ws=sockets.at(-1);ws.onopen();return ws;}
  async function flush(){for(let i=0;i<12;i++)await Promise.resolve();}
  return {states,track,audios,worklets,setMuted:(v:boolean)=>{microphoneMuted=v;return render();},cleanup,consent,flush,event:(ws:any,v:any)=>ws.onmessage({data:JSON.stringify(v)}),finishModule:()=>finishModule(),finishResume:()=>finishResume()};
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
