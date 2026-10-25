import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import PublishingReview,{isPublishingCommand,manualPublicationText} from '../src/components/PublishingReview.ts';
import type {ChatMessage} from '../src/types/recruiterChat';
const message={role:'assistant',text:'Synthetic draft',draftId:'synthetic-job',jobReference:'TT-JOB-0000000000000001',jobDescriptionResult:{job_description:{title:'Synthetic Python role',summary:'Fictional role only.',responsibilities:['Build APIs'],required_skills:['Python'],preferred_skills:['SQL'],qualifications:['API experience']}}} as ChatMessage;
function all(n:any,p:(n:any)=>boolean):any[]{if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(c=>all(c,p))];}
test('bounded chat commands prepare review; unrelated or negated prose is not a command',()=>{
 for(const s of ['/publish','publish this job','Publish to Discord and LinkedIn.','publish to other','publish to Telegram and Discord'])assert.ok(isPublishingCommand(s));
 for(const s of ['Do not publish','publish salary details','explain how to publish','publish to unknown'])assert.ok(!isPublishingCommand(s));
});
test('manual content retains full sections and original identity without claiming posting',()=>{
 const text=manualPublicationText(message);for(const s of ['TT-JOB-0000000000000001','Fictional role only.','Build APIs','Python','SQL','API experience'])assert.ok(text.includes(s));
 assert.equal(manualPublicationText({...message,jobReference:undefined}),'');
 const html=renderToStaticMarkup(h(PublishingReview,{message,busy:false,onPublish:async()=>{},onClose(){}}));
 assert.match(html,/LinkedIn — manual/);assert.match(html,/Other platform — manual/);
 assert.match(html,/Discord — automatic/);assert.match(html,/Telegram — automatic/);assert.match(html,/<textarea[^>]*readOnly/i);
 assert.match(html,/<button[^>]*disabled=""[^>]*>Confirm destinations/);
 assert.doesNotMatch(html,/checked=""|Publication confirmed|Published to LinkedIn/);
});
test('selection plus review required; confirmation calls only Discord once and manual destinations stay manual',async()=>{
 const states:any[]=[];let index=0,calls=0;
 const hooks={createElement:h,useState(v:any){const n=index++;if(!(n in states))states[n]=v;return [states[n],(next:any)=>states[n]=next];}};
 const exports:any={};const source=ts.transpileModule(readFileSync(new URL('../src/components/PublishingReview.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 runInNewContext(source,{exports,require:()=>hooks});
 const render=()=>{index=0;return exports.default({message,busy:false,onPublish:async()=>{calls++;},onClose(){}});};
 let tree=render();let inputs=all(tree,n=>n.type==='input');
 inputs[0].props.onChange();tree=render();inputs=all(tree,n=>n.type==='input');inputs[2].props.onChange();
 tree=render();let confirm=all(tree,n=>n.type==='button'&&n.props.children==='Confirm destinations')[0];assert.ok(confirm.props.disabled);
 inputs=all(tree,n=>n.type==='input');inputs[4].props.onChange();tree=render();confirm=all(tree,n=>n.type==='button'&&n.props.children==='Confirm destinations')[0];
 assert.equal(calls,0);confirm.props.onClick();await Promise.resolve();tree=render();
 assert.equal(calls,1);assert.match(renderToStaticMarkup(tree),/LinkedIn: manual action required/);
 assert.equal(all(tree,n=>n.type==='button'&&n.props.children==='Confirm destinations')[0].props.disabled,true);
});

test('reopening preview keeps confirmed Telegram receipt visible and blocks accidental repost',()=>{
 const m={...message,publications:{telegram:{status:'success' as const,result:{destination:'telegram' as const,status:'published' as const,external_id:'42'}}}};
 const html=renderToStaticMarkup(h(PublishingReview,{message:m,busy:false,onPublish:async()=>{},onClose(){}}));
 assert.match(html,/Telegram: published · 42/);
 assert.match(html,/<input[^>]*disabled=""/);
 assert.doesNotMatch(html,/Discord: published/);
});
