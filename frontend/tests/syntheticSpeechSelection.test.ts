import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import * as timing from '../src/components/interviewTime.ts';

// Same component/VM pattern as interviewFinalization.test.ts; no browser/provider.
function page(){
 const states:any[]=[],refs:any[]=[],decodes:any[]=[],cleanups:any[]=[];
 let si=0,ri=0,ei=0,authorizations=0,selected:any;const effects:any[]=[];
 const hooks={useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(x:any)=>states[i]=x];},
  useRef(v:any){const i=ri++;return refs[i]??(refs[i]={current:v});},useEffect(fn:any,deps:any[]){const i=ei++;const prior=effects[i];
   if(!prior||deps.some((d,j)=>!Object.is(d,prior[j]))){effects[i]=deps;const cleanup=fn();if(cleanup)cleanups.push(cleanup);}}};
 class Decoder{
  closed=false;
  decodeAudioData(){return new Promise((resolve,reject)=>decodes.push({resolve,reject,decoder:this}));}
  async close(){this.closed=true;}
 }
 class Room{
  remoteParticipants=new Map();localParticipant={getTrackPublication:()=>null,publishTrack:async()=>{}};
  on(){return this;}async connect(){}async disconnect(){}
 }
 const source=ts.transpileModule(readFileSync(new URL('../src/components/LiveInterviewPage.tsx',import.meta.url),'utf8').replaceAll('import.meta.env.DEV','true'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const require=createRequire(import.meta.url),exports:any={};
 runInNewContext(source,{exports,AudioContext:Decoder,window:{setInterval:()=>1,clearInterval(){}},require:(name:string)=>{
  if(name==='react')return hooks;
  if(name==='./interviewTime')return timing;
  if(name==='livekit-client')return {Room,RoomEvent:{},Track:{Source:{Camera:'camera',Microphone:'microphone'},Kind:{}},setLogLevel(){}};
  if(name==='../api/livekitInterview')return {InterviewAccessError:class extends Error{},interviewAccess:async()=>{authorizations++;return {server_url:'wss://offline.invalid',token:'synthetic'};}};
  if(name==='./syntheticInterviewMedia')return {syntheticInterviewMedia:(_role:any,speech:any)=>{selected=speech;return {audio:{},video:{},dispose(){}};}};
  if(name==='./interviewScreenShare')return {InterviewScreenShare:class{close(){}}};
  if(name.startsWith('./'))return {__esModule:true,default:()=>null};
  return require(name);
 }});
 const nodes=(n:any):any[]=>!n||typeof n!=='object'?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];
 const render=()=>{si=ri=ei=0;return exports.default({jobId:'synthetic',interview:{id:'synthetic',scheduled_at:'2030-01-01T00:00:00Z',timezone:'UTC',duration_minutes:15},onBack(){}});};
 const all=()=>nodes(render());
 const button=(label:string)=>all().find(n=>n.type==='button'&&n.props.children===label);
 const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
 const choose=async(name:string)=>{all().find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[{name,size:100,arrayBuffer:async()=>new ArrayBuffer(8)}]}});await flush();};
 all().find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked===false).props.onChange({target:{checked:true}});
 return {all,button,choose,flush,decodes,joined:()=>authorizations,selected:()=>selected,cleanup:()=>cleanups.forEach(fn=>fn())};
}

test('Join cannot authorize while the chosen WAV is decoding; the selected buffer is published',async()=>{
 const p=page();await p.choose('recruiter.wav');
 assert.equal(p.button('Join interview').props.disabled,true);
 p.button('Join interview').props.onClick();await p.flush();assert.equal(p.joined(),0);
 const speech={duration:3};p.decodes[0].resolve(speech);await p.flush();
 assert.equal(p.button('Join interview').props.disabled,false);
 p.button('Join interview').props.onClick();await p.flush();assert.equal(p.joined(),1);assert.equal(p.selected(),speech);
 assert.equal(p.decodes[0].decoder.closed,true);
});

test('a stale decode cannot replace the latest WAV; an invalid replacement clears old speech',async()=>{
 const p=page();await p.choose('old.wav');await p.choose('candidate.wav');
 const latest={duration:4};p.decodes[1].resolve(latest);await p.flush();p.decodes[0].resolve({duration:2});await p.flush();
 p.button('Join interview').props.onClick();await p.flush();assert.equal(p.selected(),latest);
 p.button('Leave interview').props.onClick();await p.flush();
 const displayed=p.all().filter(n=>n.props?.role==='status').map(n=>String(n.props.children)).join(' ');
 assert.match(displayed,/candidate.wav/);assert.doesNotMatch(displayed,/old.wav/);
 await p.choose('invalid.txt');p.button('Join interview').props.onClick();await p.flush();assert.equal(p.selected(),undefined);
 assert.ok(p.decodes.every(d=>d.decoder.closed));
});

test('unmount invalidates a pending decoder; toggling generated media retains the file-input subtree',async()=>{
 const p=page();await p.choose('recruiter.wav');p.cleanup();p.decodes[0].resolve({duration:3});await p.flush();
 assert.equal(p.button('Play generated synthetic speech').props.disabled,true);
 const toggle=p.all().find(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked===true);
 toggle.props.onChange({target:{checked:false}});
 assert.equal(p.all().filter(n=>n.type==='input'&&n.props.type==='file').length,1);
});
