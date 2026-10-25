import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {runInNewContext} from "node:vm";
import ts from "typescript";
import * as sharing from "../src/components/interviewScreenShare.ts";

test("normal Leave waits for caption finalization before the existing LiveKit disconnect",async()=>{
  const states:any[]=[],refs:any[]=[];let stateIndex=0,refIndex=0,disconnected=0,joined=0;
  const hooks={useState(initial:any){const i=stateIndex++;if(!(i in states))states[i]=initial;return [states[i],(v:any)=>{states[i]=v;}];},
    useRef(initial:any){const i=refIndex++;return refs[i]??(refs[i]={current:initial});},useEffect(){}};
  class Room{
    remoteParticipants=new Map();localParticipant={enableCameraAndMicrophone:async()=>{},getTrackPublication:()=>null};
    on(){return this;}async connect(){joined++;}async disconnect(){disconnected++;}
  }
  function Panel(){return null;}
  const source=ts.transpileModule(readFileSync(new URL("../src/components/LiveInterviewPage.tsx",import.meta.url),"utf8").replace('import.meta.env.DEV','false'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const require=createRequire(import.meta.url),exports:any={};
  runInNewContext(source,{exports,require:(name:string)=>{
    if(name==="react")return hooks;
    if(name==="./interviewScreenShare")return sharing;
    if(name==="livekit-client")return {Room,RoomEvent:{},Track:{Source:{},Kind:{}},setLogLevel(){}};
    if(name==="../api/livekitInterview")return {interviewAccess:async()=>({server_url:"wss://synthetic.invalid",token:"synthetic"})};
    if(name==="./TranscriptPanel")return {__esModule:true,default:()=>null};
    if(name==="./InterviewCopilot")return {__esModule:true,default:()=>null};
    if(name==="./InterviewAnalysis")return {__esModule:true,default:()=>null};
    if(name==="./InterviewCaptions")return {__esModule:true,default:Panel};
    if(name==="./syntheticInterviewMedia")return {syntheticInterviewMedia:()=>{throw Error("No generated/physical audio in this test");}};
    return require(name);
  }});
  function render(){stateIndex=0;refIndex=0;return exports.default({jobId:"synthetic",interview:{id:"synthetic",scheduled_at:"2030-01-01T00:00:00Z",duration_minutes:60},onBack(){}});}
  function all(node:any,p:(n:any)=>boolean):any[]{
    if(!node || typeof node!=="object")return [];
    return [...(p(node)?[node]:[]),...[node.props?.children].flat(Infinity).flatMap(n=>all(n,p))];
  }
  const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
  let tree=render();let inputs=all(tree,n=>n.type==="input");
  inputs[0].props.onChange({target:{checked:false}});inputs[1].props.onChange({target:{checked:true}});
  tree=render();all(tree,n=>n.type==="button"&&n.props.children==="Join interview")[0].props.onClick();await tick();
  assert.equal(joined,1);tree=render();
  let release=()=>{};const drained=new Promise<void>(resolve=>{release=resolve;});
  all(tree,n=>n.type===Panel)[0].props.finalizerRef.current=()=>drained;
  all(tree,n=>n.type==="button"&&n.props.children==="Leave interview")[0].props.onClick();await tick();
  assert.equal(disconnected,0);
  release();await tick();assert.equal(disconnected,1);
});

test('disconnect during initial connect does not hide sanitized stage diagnostic',async()=>{
  const states:any[]=[],refs:any[]=[];let si=0,ri=0;
  const hooks={useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(x:any)=>states[i]=x];},
    useRef(v:any){const i=ri++;return refs[i]??(refs[i]={current:v});},useEffect(){}};
  class Room{
    callback=()=>{};remoteParticipants=new Map();localParticipant={getTrackPublication:()=>null};
    on(name:any,fn:any){if(name==='disconnected')this.callback=fn;return this;}
    async connect(){this.callback();throw {reasonName:'ServerUnreachable',message:'private token must never appear'};}
    async disconnect(){}
  }
  const source=ts.transpileModule(readFileSync(new URL('../src/components/LiveInterviewPage.tsx',import.meta.url),'utf8').replace('import.meta.env.DEV','false'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const require=createRequire(import.meta.url),exports:any={};
  runInNewContext(source,{exports,require:(name:string)=>{
    if(name==='react')return hooks;
    if(name==='./interviewScreenShare')return sharing;
    if(name==='livekit-client')return {Room,RoomEvent:{Disconnected:'disconnected'},Track:{Source:{},Kind:{}},setLogLevel(){}};
    if(name==='../api/livekitInterview')return {interviewAccess:async()=>({server_url:'ws://127.0.0.1:7880',token:'synthetic'}),InterviewAccessError:class extends Error{}};
    if(name==='./syntheticInterviewMedia')return {syntheticInterviewMedia:()=>({dispose(){}})};
    if(['./TranscriptPanel','./InterviewAnalysis','./InterviewCaptions','./InterviewCopilot'].includes(name))return {__esModule:true,default:()=>null};
    return require(name);
  }});
  function render(){si=0;ri=0;return exports.default({jobId:'synthetic',interview:{id:'synthetic'},onBack(){}});}
  function all(n:any,p:(n:any)=>boolean):any[]{if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(c=>all(c,p))];}
  let tree=render();all(tree,n=>n.type==='input')[1].props.onChange({target:{checked:true}});
  tree=render();await all(tree,n=>n.type==='button'&&n.props.children==='Join interview')[0].props.onClick();
  for(let i=0;i<20;i++)await Promise.resolve();
  tree=render();const message=all(tree,n=>n.props?.role==='alert')[0].props.children;
  assert.match(message,/livekit_connection \(ServerUnreachable\)/);assert.ok(!message.includes('private token'));
});

test('remote screen subscription is separate from webcam and clears on disconnect',async()=>{
 const sdk=await import('livekit-client');
 const states:any[]=[],refs:any[]=[];let si=0,ri=0,active:any;
 const hooks={useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(x:any)=>states[i]=x];},
  useRef(v:any){return refs[ri++]??(refs[ri-1]={current:v});},useEffect(){}};
 class Room{
  events=new Map();remoteParticipants=new Map();localParticipant={getTrackPublication:()=>null,enableCameraAndMicrophone:async()=>{}};
  constructor(){active=this;}on(name:any,fn:any){this.events.set(name,fn);return this;}async connect(){}async disconnect(){}
 }
 const source=ts.transpileModule(readFileSync(new URL('../src/components/LiveInterviewPage.tsx',import.meta.url),'utf8').replace('import.meta.env.DEV','false'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const require=createRequire(import.meta.url),exports:any={};
 runInNewContext(source,{exports,require:(name:string)=>{
  if(name==='react')return hooks;
  if(name==='livekit-client')return {...sdk,Room,setLogLevel(){}};
  if(name==='./interviewScreenShare')return sharing;
  if(name==='../api/livekitInterview')return {interviewAccess:async()=>({server_url:'wss://synthetic.invalid',token:'synthetic'})};
  if(['./TranscriptPanel','./InterviewCopilot','./InterviewCaptions','./InterviewAnalysis'].includes(name))return {__esModule:true,default:()=>null};
  if(name==='./syntheticInterviewMedia')return {syntheticInterviewMedia(){throw Error('No automatic capture');}};
  return require(name);
 }});
 const nodes=(n:any):any[]=>!n||typeof n!=='object'?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];
 const render=()=>{si=ri=0;return exports.default({jobId:'synthetic',interview:{id:'synthetic'},onBack(){}});};
 const containers:any={};let tree=render();
 for(const section of nodes(tree).filter(n=>n.type==='section')){
  const heading=[section.props.children].flat().find((n:any)=>n?.type==='h2');
  const div=[section.props.children].flat().find((n:any)=>n?.type==='div'&&n.props.ref);
  if(heading&&div){const container={items:[] as any[],appendChild(e:any){this.items.push(e);},replaceChildren(){this.items=[];},get childElementCount(){return this.items.length;}};
   div.props.ref.current=container;containers[heading.props.children]=container;}
 }
 const inputs=nodes(tree).filter(n=>n.type==='input');inputs[0].props.onChange({target:{checked:false}});inputs[1].props.onChange({target:{checked:true}});
 tree=render();nodes(tree).find(n=>n.type==='button'&&n.props.children==='Join interview').props.onClick();for(let i=0;i<20;i++)await Promise.resolve();
 const makeTrack=()=>({kind:sdk.Track.Kind.Video,attach(){return {setAttribute(){},remove(){}};},detach(){return [];}});
 active.events.get(sdk.RoomEvent.TrackSubscribed)(makeTrack(),{source:sdk.Track.Source.ScreenShare});
 active.events.get(sdk.RoomEvent.TrackSubscribed)(makeTrack(),{source:sdk.Track.Source.Camera});
 assert.equal(containers['Shared screen'].items.length,1);assert.equal(containers['Remote video/audio'].items.length,1);
 active.events.get(sdk.RoomEvent.Disconnected)();
 assert.equal(containers['Shared screen'].items.length,0);assert.equal(containers['Remote video/audio'].items.length,0);
});
