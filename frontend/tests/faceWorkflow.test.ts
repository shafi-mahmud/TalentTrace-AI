import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import FaceWorkflowPanel from '../src/components/FaceWorkflowPanel.ts';
import {faceRequest,validResult} from '../src/api/faceWorkflow.ts';
const safe={similarity:.9994,provisional:true,human_review_required:true,identity_verified:false,liveness_checked:false,synthetic_only:true,decision:'no_automated_decision'};
test('disabled panel has no controls, capture or automatic consent',()=>{
 assert.equal(renderToStaticMarkup(h(FaceWorkflowPanel,{candidate:true})), '');
 for(const v of [{...safe,identity_verified:true},{...safe,similarity:NaN},{...safe,feature:[1]},{...safe,decision:'reject'}])assert.equal(validResult(v),false);
 assert.equal(validResult(safe),true);
});
test('API requests use cookies and mutation protection; errors sanitized and never retried',async t=>{
 let calls=0;
 t.mock.method(globalThis,'fetch',async(_url,init)=>{calls++;assert.equal(init?.credentials,'include');assert.equal(new Headers(init?.headers).get('X-TalentTrace-Request'),'1');return Response.json({private:'SECRET'},{status:409});});
 await assert.rejects(faceRequest('face-workflow/withdraw',{receipt:'synthetic'}),e=>e instanceof Error&&!e.message.includes('SECRET'));
 assert.equal(calls,1);
});
function harness(candidate=false){
 const slots:any[]=[],effects:any[]=[];let index=0,reply:any=candidate?{state:'not_enrolled',wording:'Optional synthetic samples only.',version:'synthetic-face-workflow-v1',interview_id:'synthetic-interview'}:{state:'enrolled',run_id:'synthetic-run',expires_at:Date.now()/1000+60,viva_authorized:true};
 const calls:any[]=[];let poll:any,heldRead:Promise<any>|null=null;const exports:any={};
 const hooks={createElement:h,useRef(v:any){return hooks.useState({current:v})[0];},useState(v:any){const n=index++;if(!(n in slots))slots[n]=v;return [slots[n],(v:any)=>slots[n]=v];},useEffect(f:any,d:any[]){const n=index++;if(!slots[n]){slots[n]=d;effects.push(f);}}};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/FaceWorkflowPanel.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 runInNewContext(source,{exports,Date,setInterval:(f:any)=>{poll=f;return 1;},clearInterval(){},require:(name:string)=>name==='react'?hooks:{validResult,faceRequest:async(path:string,body?:any)=>{calls.push([path,body]);if(body===undefined&&heldRead)return await heldRead;if(body&&path.endsWith('/verify'))return safe;if(path.endsWith('/consent')&&body)return {withdrawal_receipt:'private-synthetic-receipt'};return reply;}}});
 function render(){index=0;return exports.default({candidate,jobId:'job',interviewId:'synthetic-interview'});}
 function all(n:any):any[]{return n&&typeof n==='object'?[n,...[n.props?.children].flat(Infinity).flatMap(all)]:[];}
 const flush=async()=>{for(let n=0;n<20;n++)await Promise.resolve();};
 async function load(){render();effects.splice(0).forEach(f=>f());await flush();return render();}
 return {render,all,flush,load,calls,holdRead(p:Promise<any>|null){heldRead=p;},poll:()=>poll(),setReply(v:any){reply=v;}};
}
test('candidate consent is unchecked and explicit, with no upload or token display',async()=>{
 const x=harness(true);let tree=await x.load();let nodes=x.all(tree);
 assert.equal(nodes.find(n=>n.type==='input').props.checked,false);
 assert.equal(nodes.find(n=>n.type==='button').props.disabled,true);
 assert.equal(x.calls.filter(c=>c[1]).length,0);
 nodes.find(n=>n.type==='input').props.onChange({target:{checked:true}});tree=x.render();
 x.all(tree).find(n=>n.type==='button').props.onClick();await x.flush();
 assert.equal(x.calls.filter(c=>c[1])[0][1].accepted,true);
 assert.doesNotMatch(renderToStaticMarkup(x.render()),/private-synthetic-receipt|type="file"/);
});
test('recruiter sees provisional output after human review; withdrawal status clears it',async()=>{
 const x=harness();let tree=await x.load();let nodes=x.all(tree);
 assert.equal(nodes.find(n=>n.type==='button').props.disabled,true);
 nodes.find(n=>n.type==='input').props.onChange({target:{checked:true}});tree=x.render();
 x.all(tree).find(n=>n.type==='button').props.onClick();await x.flush();
 assert.match(renderToStaticMarkup(x.render()),/Provisional similarity: 0.9994/);
 x.setReply({state:'withdrawn'});x.poll();await x.flush();
 assert.doesNotMatch(renderToStaticMarkup(x.render()),/Provisional similarity/);
});

test('candidate can withdraw a restored enrollment without a receipt or renewed consent',async()=>{
 const x=harness(true);await x.load();
 x.setReply({state:'enrolled',run_id:'restored-run',interview_id:'synthetic-interview',expires_at:Date.now()/1000+60});
 x.poll();await x.flush();
 const button=x.all(x.render()).find(n=>n.type==='button'&&n.props.children==='Withdraw and delete reference');
 assert.ok(button);assert.notEqual(button.props.disabled,true);
 button.props.onClick();await x.flush();
 const call=x.calls.find(c=>c[0].endsWith('/withdraw'));
 assert.equal(call[0],'interview-access/face-workflow/withdraw');assert.equal(call[1].run_id,'restored-run');
 assert.doesNotMatch(renderToStaticMarkup(x.render()),/Synthetic reference enrolled|Provisional similarity/);
});

test('a late status response cannot revive a deleted reference; overlapping polls are suppressed',async()=>{
 const x=harness();await x.load();let resolve!:(v:any)=>void;
 x.holdRead(new Promise(r=>{resolve=r;}));x.poll();const calls=x.calls.length;x.poll();assert.equal(x.calls.length,calls);
 x.holdRead(null);x.setReply({state:'not_enrolled'});
 x.all(x.render()).find(n=>n.type==='button'&&n.props.children==='Delete reference').props.onClick();await x.flush();
 resolve({state:'enrolled',run_id:'old-run',expires_at:Date.now()/1000+60,viva_authorized:true});await x.flush();
 assert.doesNotMatch(renderToStaticMarkup(x.render()),/Synthetic reference enrolled|Provisional similarity/);
});
