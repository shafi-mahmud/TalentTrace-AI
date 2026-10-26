import test from 'node:test';
import assert from 'node:assert/strict';
import {activity,observeActivity} from '../src/components/interviewActivityObserver.ts';

function documentDouble(){return Object.assign(new EventTarget(),{visibilityState:'visible',fullscreenEnabled:true,fullscreenElement:null}) as unknown as Document;}
const tick=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
test('coarse status supports visibility/fullscreen and does not inspect other tabs',()=>{
 const d=documentDouble();assert.deepEqual(activity(d),{visibility:'visible',fullscreen:'inactive'});
 Object.assign(d,{visibilityState:'hidden',fullscreenElement:{}});assert.deepEqual(activity(d),{visibility:'hidden',fullscreen:'active'});
 Object.assign(d,{visibilityState:'unknown',fullscreenEnabled:false});assert.deepEqual(activity(d),{visibility:'unsupported',fullscreen:'unsupported'});
});
test('explicit observation reports current state, serializes updates and cleanup stops reporting',async()=>{
 const d=documentDouble(),sent:any[]=[];let release!:()=>void;
 const stop=observeActivity(d,async v=>{sent.push(v);if(sent.length===1)await new Promise<void>(r=>{release=r;});},()=>assert.fail('No failure'));
 Object.assign(d,{visibilityState:'hidden'});d.dispatchEvent(new Event('visibilitychange'));
 Object.assign(d,{fullscreenElement:{}});d.dispatchEvent(new Event('fullscreenchange'));assert.equal(sent.length,1);
 release();await tick();assert.equal(sent.length,2);assert.deepEqual(sent[1],{visibility:'hidden',fullscreen:'active'});
 stop();d.dispatchEvent(new Event('visibilitychange'));await tick();assert.equal(sent.length,2);
});
test('failure stops observation and does not resume automatically',async()=>{
 const d=documentDouble();let calls=0,errors=0;
 const stop=observeActivity(d,async()=>{calls++;throw Error('PRIVATE');},()=>{errors++;});await tick();
 d.dispatchEvent(new Event('visibilitychange'));await tick();assert.equal(calls,1);assert.equal(errors,1);stop();
});

test('candidate consent is explicit and late consent after disconnect is withdrawn',async()=>{
 const {readFileSync}=await import('node:fs');const {runInNewContext}=await import('node:vm');
 const ts=(await import('typescript')).default;const {createElement}=await import('react');
 const states:any[]=[],refs:any[]=[],deps:any[][]=[],cleanups:any[]=[],effects:any[]=[];let si=0,ri=0,ei=0,resolve!:(v:string)=>void;
 let consents=0,withdrawals=0,observed=0;
 const hooks={useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(v:any)=>states[i]=v];},useRef(v:any){return refs[ri++]??(refs[ri-1]={current:v});},
  useEffect(fn:any,next:any[]){const i=ei++;if(!deps[i]||next.some((v,j)=>v!==deps[i][j])){cleanups[i]?.();deps[i]=next;effects.push(()=>{cleanups[i]=fn();});}}};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/InterviewActivity.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const exports:any={};const api={consent:()=>{consents++;return new Promise<string>(r=>resolve=r);},withdraw:async()=>{withdrawals++;},send:async()=>{}};
 const jsx=await import('react/jsx-runtime');
 runInNewContext(source,{exports,document:documentDouble(),require:(name:string)=>name==='react'?hooks:name==='react/jsx-runtime'?jsx:name==='../api/interviewAttention'?api:{observeActivity(){observed++;return()=>{};}}});
 const nodes=(n:any):any[]=>!n||typeof n!=='object'?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];
 const render=(connected=true)=>{si=ri=ei=0;const tree=exports.default({candidate:true,connected});while(effects.length)effects.shift()();return tree;};
 let tree=render();assert.equal(consents,0);assert.equal(observed,0);
 const input=nodes(tree).find(n=>n.type==='input');assert.equal(input.props.checked,false);
 input.props.onChange({target:{checked:true}});tree=render();nodes(tree).find(n=>n.type==='button'&&n.props.children==='Share status').props.onClick();
 assert.equal(consents,1);render(false);resolve('synthetic-run');await tick();
 assert.equal(observed,0);assert.equal(withdrawals,1);for(const cleanup of cleanups)cleanup?.();
});
