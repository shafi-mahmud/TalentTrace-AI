import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {runInNewContext} from "node:vm";
import ts from "typescript";

test("normal Leave waits for caption finalization before the existing LiveKit disconnect",async()=>{
  const states:any[]=[],refs:any[]=[];let stateIndex=0,refIndex=0,disconnected=0,joined=0;
  const hooks={useState(initial:any){const i=stateIndex++;if(!(i in states))states[i]=initial;return [states[i],(v:any)=>{states[i]=v;}];},
    useRef(initial:any){const i=refIndex++;return refs[i]??(refs[i]={current:initial});},useEffect(){}};
  class Room{
    remoteParticipants=new Map();localParticipant={enableCameraAndMicrophone:async()=>{},getTrackPublication:()=>null};
    on(){return this;}async connect(){joined++;}async disconnect(){disconnected++;}
  }
  function Panel(){return null;}
  const source=ts.transpileModule(readFileSync(new URL("../src/components/LiveInterviewPage.tsx",import.meta.url),"utf8"),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const require=createRequire(import.meta.url),exports:any={};
  runInNewContext(source,{exports,require:(name:string)=>{
    if(name==="react")return hooks;
    if(name==="livekit-client")return {Room,RoomEvent:{},Track:{Source:{},Kind:{}},setLogLevel(){}};
    if(name==="../api/livekitInterview")return {interviewAccess:async()=>({server_url:"wss://synthetic.invalid",token:"synthetic"})};
    if(name==="./TranscriptPanel")return {__esModule:true,default:()=>null};
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
