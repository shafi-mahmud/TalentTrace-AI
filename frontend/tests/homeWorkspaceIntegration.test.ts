import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import * as navigation from '../src/state/workspaceNavigation.ts';
import * as workspace from '../src/state/recruiterWorkspace.ts';
import {workingJob} from '../src/api/jobs.ts';
import type {SavedJob} from '../src/api/jobs';

const jobs:SavedJob[]=[1,2].map(i=>({id:`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`,
 job_reference:`TT-JOB-${String(i).padStart(16,'0')}`,job_title:`Synthetic job ${i}`,revision:1,
 suggestions:{job_title:`Synthetic job ${i}`,criteria:[{criterion_id:'python',description:'Python',category:'skill',is_hard:true}]},sources:[],snapshot:null,draft:null,
 conversation_id:`00000000-0000-4000-8000-${String(i+10).padStart(12,'0')}`}));
function all(n:any,p:(n:any)=>boolean):any[]{if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(c=>all(c,p))];}

test('actual workspace restores Home, opens the selected conversation, and carries the returned job to screening',async()=>{
 const slots:any[]=[],effects:(()=>unknown)[]=[];let index=0,loads=0;
 const memory=new Map([['talenttrace-active-job:owner',jobs[0].id]]);
 const hooks:any={useState(v:any){const i=index++;if(!(i in slots))slots[i]=typeof v==='function'?v():v;return [slots[i],(n:any)=>{slots[i]=typeof n==='function'?n(slots[i]):n;}];},
 useReducer(reduce:any,value:any,init:any){const [s,set]=hooks.useState(()=>init?init(value):value);return [s,(a:any)=>set((p:any)=>reduce(p,a))];},
 useRef(v:any){return hooks.useState({current:v})[0];},useEffect(fn:any,deps:any[]){const i=index++;if(!slots[i]||deps.some((v,j)=>!Object.is(v,slots[i][j]))){slots[i]=deps;effects.push(fn);}},lazy:()=>()=>null,Suspense:()=>null};
 const panels=new Map<string,any>();
 const panel=(name:string)=>{if(!panels.has(name))panels.set(name,()=>null);return panels.get(name);};
 const require=createRequire(import.meta.url),exports:any={};
 const source=ts.transpileModule(readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8').replace('function Workspace(', 'export function Workspace('),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const browser={location:{hash:'#home',pathname:'/',search:''},history:{replaceState(){}},sessionStorage:{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v),removeItem:(k:string)=>memory.delete(k)},addEventListener(){},removeEventListener(){}};
 runInNewContext(source,{exports,window:browser,require:(name:string)=>{
  if(name==='react')return hooks;
  if(name==='./api/jobs')return {workingJob,listJobs:async()=>{loads++;return jobs;}};
  if(name==='./state/recruiterWorkspace')return workspace;
  if(name==='./state/workspaceNavigation')return navigation;
  if(name==='./components/cvIntakePresentation')return {WorkspaceNavigation:panel('nav')};
  if(name==='./components/chatPresentation')return {RecruiterChatPage:panel('chatPage')};
  if(name.startsWith('./'))return {__esModule:true,default:panel(name)};
  return require(name);
 }});
 function render(){index=0;return exports.Workspace({recruiterId:'owner',accountControls:null});}
 async function settle(){for(let n=0;n<3;n++){render();for(const fn of effects.splice(0))fn();for(let i=0;i<10;i++)await Promise.resolve();}return render();}
 function home(tree:any){return all(tree,n=>n.type===panel('./components/RecruiterHome'))[0];}
 function chat(tree:any){return all(tree,n=>n.type===panel('./components/RecruiterChat'))[0];}
 let tree=await settle();assert.equal(home(tree).props.activeJobId,jobs[0].id);assert.equal(home(tree).props.jobs.length,2);
 home(tree).props.onOpen(jobs[1],'jd');tree=render();
 assert.equal(chat(tree).props.initialConversationId,jobs[1].conversation_id);
 assert.equal(all(tree,n=>n.type===panel('./components/CvIntake'))[0].props.draft.draftId,jobs[1].id);
 all(tree,n=>n.type===panel('nav'))[0].props.onChange('home');tree=render();home(tree).props.onReload();tree=await settle();assert.ok(loads>=2);
 home(tree).props.onCreate();tree=render();assert.equal(chat(tree).props.initialConversationId,undefined);
 assert.equal(all(tree,n=>n.type===panel('./components/CvIntake'))[0].props.draft,null);
 chat(tree).props.onDraftGenerated({...workingJob(jobs[0]),revision:3,reviewed:false});tree=render();
 all(tree,n=>n.type===panel('nav'))[0].props.onChange('cv');tree=render();
 const selected=all(tree,n=>n.type===panel('./components/CvIntake'))[0].props.draft;
 assert.equal(selected.draftId,jobs[0].id);assert.equal(selected.jobReference,jobs[0].job_reference);assert.equal(selected.revision,3);assert.equal(selected.reviewed,false);
});
