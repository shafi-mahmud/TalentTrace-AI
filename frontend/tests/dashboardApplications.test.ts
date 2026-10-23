import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {createElement as h,Fragment} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
import RecruiterHome from '../src/components/RecruiterHome.ts';
import ApplicationNotifications,{ApplicationSummary} from '../src/components/ApplicationNotifications.ts';
import {validateApplications} from '../src/api/applications.ts';
import type {Applications} from '../src/api/applications.ts';
import type {SavedJob} from '../src/api/jobs';
const job='00000000-0000-4000-8000-000000000001';
const uuid=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
function summary(n=1):Applications {return {job_id:job,received_count:n,new_count:n,unavailable_count:0,invalid_batch_count:0,
 applications:Array.from({length:n},(_,i)=>({batch_id:uuid(2),upload_id:uuid(i+3),origin:i%2?'native_storage':'trusted_import',available:true,is_new:true}))};}
function all(n:any,p:(n:any)=>boolean):any[]{if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(c=>all(c,p))];}
function harness(initial:any=summary()){
 const states:any[]=[],refs:any[]=[],effects:any[]=[];let si=0,ri=0,loads=0,marks:any[]=[],next=initial,fail=false,markFail=false;
 let release:(value:any)=>void=()=>{};
 const hooks={createElement:h,Fragment,useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(x:any)=>states[i]=x];},
  useRef(v:any){const i=ri++;return refs[i]??(refs[i]={current:v});},useEffect(fn:any){effects.push(fn);}};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/ApplicationNotifications.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const exports:any={};runInNewContext(source,{exports,require:(name:string)=>name==='react'?hooks:{
  async loadApplications(){loads++;if(fail)throw Error('PRIVATE');if(next===null)return new Promise(resolve=>{release=resolve;});return next;},
  async markApplicationsViewed(_job:string,rows:any[]){marks.push(rows);if(markFail)throw Error('PRIVATE');next={...next,new_count:next.applications.filter((r:any)=>!rows.some(a=>a.upload_id===r.upload_id)).length,applications:next.applications.map((r:any)=>({...r,is_new:!rows.some(a=>a.upload_id===r.upload_id)}))};}
 }});
 function render(id=job){si=ri=0;return exports.default({jobId:id});}
 const click=(label:string)=>all(render(),n=>n.type==='button'&&n.props.children===label)[0].props.onClick();
 const text=()=>renderToStaticMarkup(render());
 const flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
 render();const cleanup=effects[0]();
 return {render,text,click,flush,cleanup,resolve:(v:any)=>release(v),setNext(v:any){next=v;},fail(){fail=true;},markFail(){markFail=true;},counts:()=>({loads,marks})};
}
test('operational cards and breakdown reconcile native/imported/unavailable counts',()=>{
 const data=summary(3);data.applications[0].available=false;data.unavailable_count=1;
 const html=renderToStaticMarkup(h(ApplicationSummary,{data}));
 for(const text of ['CVs received','New / unviewed','Available CVs','Imported CVs needing attention','Native upload','Trusted import','<meter'])assert.ok(html.includes(text),text);
 assert.equal(data.received_count,data.applications.length);assert.match(html,/<dd>3<\/dd>/);assert.match(html,/<dd>2<\/dd>/);assert.match(html,/<dd>1<\/dd>/);
});
test('Home requests only selected saved job and navigation carries that job',()=>{
 const jobs=[1,2].map(i=>({id:uuid(i),job_reference:`TT-JOB-${String(i).padStart(16,'0')}`,job_title:`Synthetic ${i}`,revision:1,snapshot:null,conversation_id:null})) as SavedJob[];
 let opened:any;const props={jobs,activeJobId:job,loading:false,error:'',onReload(){},onCreate(){},onSelect(){},onOpen(j:any,m:any){opened=[j.id,m];}};
 const tree=RecruiterHome(props);assert.equal(all(tree,n=>n.type===ApplicationNotifications).length,1);
 assert.equal(all(tree,n=>n.type===ApplicationNotifications)[0].props.jobId,job);
 all(tree,n=>n.type==='button'&&n.props.children==='Continue to Candidate Screening')[0].props.onClick();assert.deepEqual(opened,[job,'cv']);
 assert.equal(all(RecruiterHome({...props,activeJobId:uuid(2)}),n=>n.type===ApplicationNotifications)[0].props.jobId,uuid(2));
 assert.equal(all(RecruiterHome({...props,error:'Unavailable'}),n=>n.type===ApplicationNotifications).length,0);
});
test('loading, zero, missing and stale/error states never substitute invented zero',async()=>{
 const loading=harness(null);assert.match(loading.text(),/Updating applications/);assert.doesNotMatch(loading.text(),/CVs received/);loading.cleanup();loading.resolve(summary());await loading.flush();assert.doesNotMatch(loading.text(),/CVs received/);
 const empty=harness(summary(0));await empty.flush();assert.match(empty.text(),/No applications received yet/);
 const missing=harness();missing.fail();await missing.flush();missing.click('Refresh applications');await missing.flush();assert.match(missing.text(),/Last loaded snapshot/);assert.match(missing.text(),/Applications unavailable/);assert.doesNotMatch(missing.text(),/PRIVATE/);
});
test('opening and refresh are read-only; acknowledge only the displayed bounded snapshot, preserve late arrival',async()=>{
 const x=harness(summary(26));await x.flush();assert.equal(x.counts().marks.length,0);
 x.click('Refresh applications');await x.flush();assert.equal(x.counts().marks.length,0);
 x.setNext(summary(27));x.click('Mark displayed applications as viewed');x.click('Mark displayed applications as viewed');await x.flush();
 assert.equal(x.counts().marks.length,1);assert.equal(x.counts().marks[0].length,25);
 assert.match(x.text(),/Showing 25 of 27/);x.click('Show more applications');assert.match(x.text(),/Showing 27 of 27/);assert.match(x.text(),/New/);
});
test('unconfirmed acknowledgement blocks repetition until refresh and hides foreign-job data',async()=>{
 const x=harness();await x.flush();x.markFail();x.click('Mark displayed applications as viewed');await x.flush();
 assert.match(x.text(),/Viewed status was not confirmed/);x.click('Mark displayed applications as viewed');assert.equal(x.counts().marks.length,1);
 assert.equal(all(x.render(uuid(9)),n=>n.type===ApplicationSummary).length,0);
});
test('unknown sensitive fields and invalid counts are rejected, rather than retained in analytics',()=>{
 for(const bad of [{...summary(),email:'private@example.test'},{...summary(),applications:[{...summary().applications[0],cv_text:'PRIVATE'}]}, {...summary(),new_count:99}])assert.throws(()=>validateApplications(bad,job));
 const html=renderToStaticMarkup(h(ApplicationSummary,{data:summary()}));assert.doesNotMatch(html,/upload_id|batch_id|cookie|@|PRIVATE/);
});
