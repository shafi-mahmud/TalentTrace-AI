import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import AppointmentEmail from '../src/components/AppointmentEmail.ts';
import {emailLabels,emailStatus,previewEmail,sendEmail} from '../src/api/appointmentEmail.ts';
import type {Interview} from '../src/api/interviews.ts';
const id='00000000-0000-4000-8000-000000000001';
const row:Interview={id,job_id:id,job_reference:'TT-JOB-0000000000000001',batch_id:id,upload_id:id,criteria_revision:2,scoring_version:'f2-coverage-v1',scheduled_at:'2099-11-20T09:00:00Z',timezone:'Asia/Dhaka',duration_minutes:60,unscored_confirmed:false,status:'scheduled'};
const review={subject:'Synthetic appointment',body:'Job Reference: '+row.job_reference+' Start: 15:00 End: 16:00 Asia/Dhaka. Appointment only. No joining access.',review_digest:'a'.repeat(64),contact_status:'no_recorded_contact',recipient_mask:'a***@synthetic.invalid'};
const all=(n:any,p:(v:any)=>boolean):any[]=>!n||typeof n!=='object'?[]:[...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(x=>all(x,p))];
function harness({initial='none',send='accepted',reject=false,defer=false,recorded=false}:any={}){
 const states:any[]=[],refs:any[]=[];let si=0,ri=0,writes=0,reads=0,previews=0,resolve:any;
 const hooks={createElement:h,useState(v:any){const i=si++;if(!(i in states))states[i]=v;return [states[i],(x:any)=>states[i]=typeof x==='function'?x(states[i]):x];},useRef(v:any){const i=ri++;return refs[i]??(refs[i]={current:v});},useEffect(){}};
 const api={emailLabels,async emailStatus(){reads++;return initial;},async previewEmail(job:string,interview:string,recipient:string){previews++;assert.equal(job,id);assert.equal(interview,id);assert.equal(recipient,'approved@synthetic.invalid');if(reject)throw Error('Enter an explicitly approved recipient.');return {...review,contact_status:recorded?'matches_recorded':'no_recorded_contact'};},async sendEmail(){writes++;if(defer)await new Promise(r=>resolve=r);return send;}};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/AppointmentEmail.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const require=createRequire(import.meta.url),exports:any={};runInNewContext(source,{exports,require:(name:string)=>name==='react'?hooks:name==='../api/appointmentEmail.ts'?api:require(name)});
 function render(){si=0;ri=0;return exports.default({interview:row});}
 const button=(text:string)=>all(render(),x=>x.type==='button'&&x.props.children===text)[0];
 const input=(type:string)=>all(render(),x=>x.type==='input'&&x.props.type===type)[0];
 return {render,button,input,get writes(){return writes;},get reads(){return reads;},get previews(){return previews;},release(){resolve?.();}};
}
async function prepare(x:ReturnType<typeof harness>){await x.button('Review appointment email').props.onClick();await new Promise(r=>setImmediate(r));x.input('email').props.onChange({target:{value:'approved@synthetic.invalid'}});await x.button('Preview saved appointment').props.onClick();await new Promise(r=>setImmediate(r));}

test('saved interview email is explicit and makes no request on ordinary rendering',()=>{
 const x=harness();x.render();assert.equal(x.reads,0);assert.equal(x.writes,0);
 const html=renderToStaticMarkup(h(AppointmentEmail,{interview:row}));assert.match(html,/Review appointment email/);assert.doesNotMatch(html,/approved@|Send appointment confirmation/);
});
test('preview requires separate confirmation; duplicate clicks send once',async()=>{
 const x=harness({defer:true});await prepare(x);assert.equal(x.writes,0);assert.equal(x.previews,1);assert.match(JSON.stringify(x.render()),/No recorded application contact/);
 assert.equal(x.button('Send appointment confirmation').props.disabled,true);
 x.button('Send appointment confirmation').props.onClick();assert.equal(x.writes,0);
 x.input('checkbox').props.onChange({target:{checked:true}});
 const click=x.button('Send appointment confirmation').props.onClick;click();click();assert.equal(x.writes,1);
 x.release();await new Promise(r=>setImmediate(r));assert.equal(x.button('Send appointment confirmation'),undefined);
 const text=JSON.stringify(x.render());assert.match(text,/Accepted by SMTP/);assert.match(text,/does not prove mailbox delivery/);assert.doesNotMatch(text,/approved@/);
});
test('recipient edit invalidates review and confirmation',async()=>{
 const x=harness();await prepare(x);x.input('checkbox').props.onChange({target:{checked:true}});x.input('email').props.onChange({target:{value:'changed@synthetic.invalid'}});
 assert.equal(x.button('Send appointment confirmation'),undefined);assert.equal(x.writes,0);
});
for(const status of ['accepted','failed','uncertain','not_configured'])test(`persisted ${status} offers no send on reload`,async()=>{
 const x=harness({initial:status});await x.button('Review appointment email').props.onClick();await new Promise(r=>setImmediate(r));
 assert.equal(x.input('email'),undefined);assert.equal(x.writes,0);assert.match(JSON.stringify(x.render()),new RegExp(emailLabels[status as keyof typeof emailLabels]));
});
test('rejected preview and uncertain send expose safe status without repeat action',async()=>{
 const rejected=harness({reject:true});await prepare(rejected);assert.equal(rejected.button('Send appointment confirmation'),undefined);assert.equal(rejected.writes,0);
 const x=harness({send:'uncertain'});await prepare(x);x.input('checkbox').props.onChange({target:{checked:true}});x.button('Send appointment confirmation').props.onClick();await new Promise(r=>setImmediate(r));
 assert.match(JSON.stringify(x.render()),/Delivery uncertain/);assert.equal(x.button('Send appointment confirmation'),undefined);
});
test('API contracts bind exact IDs, reject extra sensitive fields and sanitize ambiguous responses',async()=>{
 const original=globalThis.fetch;const calls:any[]=[];
 try{
  globalThis.fetch=(async(url:any,init:any)=>{calls.push({url,init});return new Response(JSON.stringify({email_status:'accepted'}));}) as any;
  assert.equal(await emailStatus(id,id),'accepted');assert.match(calls[0].url,new RegExp(`/jobs/${id}/interviews/${id}/appointment-email$`));
  globalThis.fetch=(async()=>new Response(JSON.stringify({...review,cookie:'PRIVATE'}))) as any;
  await assert.rejects(previewEmail(id,id,'approved@synthetic.invalid'),/Preview unavailable/);
  globalThis.fetch=(async()=>new Response('PRIVATE bearer malformed')) as any;await assert.rejects(previewEmail(id,id,'approved@synthetic.invalid'),/Preview unavailable/);
  globalThis.fetch=(async()=>{throw Error('PRIVATE bearer');}) as any;await assert.rejects(previewEmail(id,id,'approved@synthetic.invalid'),/Preview unavailable/);assert.equal(await sendEmail(id,id,'approved@synthetic.invalid',review),'uncertain');
  globalThis.fetch=(async()=>new Response('PRIVATE',{status:503})) as any;assert.equal(await sendEmail(id,id,'approved@synthetic.invalid',review),'not_configured');
  globalThis.fetch=(async()=>new Response(JSON.stringify({email_status:'accepted',token:'PRIVATE'}))) as any;assert.equal(await sendEmail(id,id,'approved@synthetic.invalid',review),'uncertain');
 }finally{globalThis.fetch=original;}
});


test('recorded contact is masked and explicitly not mailbox verification',async()=>{
 const x=harness({recorded:true});await prepare(x);
 const text=all(x.render(),n=>n.type==='p').map(n=>n.props.children).join(' ');
 assert.match(text,/Matches the recorded imported application contact/);
 assert.match(text,/does not verify mailbox ownership/);
 assert.match(text,/a\*\*\*@synthetic.invalid/);
 assert.doesNotMatch(text,/approved@synthetic.invalid/);
});
