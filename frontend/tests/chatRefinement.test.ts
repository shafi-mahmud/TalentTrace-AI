import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
import {replyToChatMessage,ChatMessageView} from '../src/components/chatPresentation.ts';
import * as presentation from '../src/components/chatPresentation.ts';
import ProviderSelection from '../src/components/ProviderSelection.ts';
import * as publishingReview from '../src/components/PublishingReview.ts';
import * as chatState from '../src/state/recruiterChatState.ts';
import {copyJobReference} from '../src/components/SavedJobIdentity.ts';
import {RecruiterChatRequestError} from '../src/api/recruiterChat.ts';
import type {RecruiterChatResponse,WorkingCriteriaDraft} from '../src/types/recruiterChat';

const id='00000000-0000-4000-8000-000000000001',conversation='00000000-0000-4000-8000-000000000002',reference='TT-JOB-0123456789ABCDEF';
function reply(revision=1):RecruiterChatResponse{return {status:'jd_generated',intent:'create_job_description',conversation_id:conversation,draft_id:id,job_reference:reference,job_revision:revision,assistant_message:'Draft ready.',publishing_context:{},
 screening_suggestions:{job_title:'Engineer',criteria:[{criterion_id:'python',description:'Python',category:'skill',is_hard:true}]},screening_suggestion_sources:[],
 job_description_result:{status:'draft',human_review_required:true,provider:'groq',model:'synthetic',retrieval_mode:'semantic_bge_pgvector',
 job_description:{title:'Engineer',summary:'Build services.',responsibilities:['Write tests'],required_skills:['Python'],preferred_skills:[],qualifications:['Backend skills'],policy_citation_ids:['synthetic']},
 grounding_citations:[{citation_id:'synthetic',source_title:'Synthetic policy',heading_paths:[['Skills']]}]}};}
function all(n:any,p:(n:any)=>boolean):any[]{if(!n||typeof n!=='object')return [];return [...(p(n)?[n]:[]),...[n.props?.children].flat(Infinity).flatMap(c=>all(c,p))];}
const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
function harness(send:(text:string,c?:string)=>Promise<RecruiterChatResponse>,restore=async()=>({id:conversation,turns:[{message:'Original instruction',reply:reply()}]}),initialConversationId?:string,publish:(...args:any[])=>Promise<any>=async()=>{throw Error("Publication forbidden");}){
 const slots:any[]=[],effects:(()=>unknown)[]=[];let index=0;const drafts:Record<string,WorkingCriteriaDraft>={};const continued:string[]=[];
 const hooks={useState(v:any){const i=index++;if(!(i in slots))slots[i]=typeof v==='function'?v():v;return [slots[i],(n:any)=>{slots[i]=typeof n==='function'?n(slots[i]):n;}];},
 useReducer(reduce:any,initial:any){const [value,set]=hooks.useState(initial);return [value,(a:any)=>set((s:any)=>reduce(s,a))];},
 useRef(v:any){return hooks.useState({current:v})[0];},useEffect(fn:any,deps:any[]){const i=index++;if(!slots[i]||deps.some((v,j)=>!Object.is(v,slots[i][j]))){slots[i]=deps;effects.push(fn);}}};
 const source=ts.transpileModule(readFileSync(new URL('../src/components/RecruiterChat.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const require=createRequire(import.meta.url),exports:any={};
 runInNewContext(source,{exports,crypto:globalThis.crypto,window:{confirm:()=>true},require:(name:string)=>{
  if(name==='react')return hooks;
  if(name==='./ProviderSelection')return {__esModule:true,default:ProviderSelection};
  if(name==='./PublishingReview')return {__esModule:true,...publishingReview};
  if(name==='../api/recruiterChat')return {isValidRecruiterMessage:(s:string)=>!!s.trim(),RecruiterChatRequestError,sendRecruiterMessage:send};
  if(name==='../api/jobs')return {listConversations:async()=>[],loadConversation:restore};
  if(name==='./chatPresentation')return presentation;
  if(name==='../state/recruiterChatState')return chatState;
  if(name==='../api/jobPublishing')return {publishDraft:publish};
  return require(name);
 }});
 const props={drafts,initialConversationId,onConversationLoaded(){},onDraftGenerated:(d:WorkingCriteriaDraft)=>{drafts[d.draftId]=d;},onCriteriaChange(){},onCriteriaReviewed(){},onContinueToCv:(value:string)=>continued.push(value),onNewChat(){}};
 function render(){index=0;return exports.default(props);}
 async function submit(text:string){let tree=render();const provider=all(tree,n=>n.type===ProviderSelection)[0];provider.props.onChange('groq');provider.props.onConsent(true);tree=render();all(tree,n=>n.type==='textarea')[0].props.onChange({target:{value:text}});tree=render();await all(tree,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});await tick();return render();}
 async function flush(){for(const fn of effects.splice(0))fn();await tick();}
 return {render,submit,flush,drafts,continued};
}

test('server job reference and revision are visible; internal UUID is separately labelled',()=>{
 const message=replyToChatMessage(reply(3));assert.equal(message.jobReference,reference);assert.equal(message.jobRevision,3);
 const html=renderToStaticMarkup(h(ChatMessageView,{message}));
 assert.match(html,/Draft saved under Job Reference/);assert.ok(html.includes(reference));assert.match(html,/Revision 3/);assert.match(html,/Internal UUID \(not the Job Reference\)/);
 const legacy=reply();if(legacy.status==='jd_generated'){delete legacy.job_reference;delete legacy.job_revision;}
 assert.match(renderToStaticMarkup(h(ChatMessageView,{message:replyToChatMessage(legacy)})),/Saved job identity unavailable/);
});
test('copy writes only the returned reference and handles clipboard failure safely',async()=>{
 const writes:string[]=[];assert.equal(await copyJobReference(reference,async text=>{writes.push(text);}), 'Job Reference copied.');assert.deepEqual(writes,[reference]);
 assert.match(await copyJobReference(reference,async()=>{throw Error('private detail');}),/Copy unavailable/);
 assert.equal(await copyJobReference(id,async()=>assert.fail('Invalid reference copied')),'Job Reference unavailable.');
});
test('specific revisions send in the same conversation and expose only the latest criteria action',async()=>{
 const calls:any[]=[];const h=harness(async(text,c)=>{calls.push([text,c]);return reply(calls.length);});
 await h.submit('Create a job');h.drafts[id].reviewed=true;
 const other={...h.drafts[id],draftId:'other-job',reviewed:true};h.drafts['other-job']=other;
 let tree=h.render();all(tree,n=>n.type===ChatMessageView)[0].props.onRevise();
 tree=h.render();assert.equal(all(tree,n=>n.type==='textarea')[0].props.value,'');
 tree=await h.submit('Change the required experience to 3 years and add Docker as a preferred skill.');
 assert.equal(calls[1][1],conversation);assert.equal(h.drafts[id].revision,2);assert.equal(h.drafts[id].jobReference,reference);assert.equal(h.drafts[id].reviewed,false);assert.equal(h.drafts['other-job'],other);
 const messages=all(tree,n=>n.type===ChatMessageView);const cards=messages.filter(n=>n.props.message.jobDescriptionResult);
 assert.equal(cards[0].props.actionsDisabled,true);cards[1].props.onContinue();assert.deepEqual(h.continued,[id]);
});
test('uncertain revision retains the saved draft and never automatically sends again',async()=>{
 let calls=0;const h=harness(async()=>{calls++;if(calls===1)return reply();throw new RecruiterChatRequestError('Unconfirmed',true,true);});
 await h.submit('Create a job');const before=h.drafts[id];const tree=await h.submit('Add Docker');
 await h.flush();assert.equal(calls,2);assert.equal(h.drafts[id],before);assert.equal(all(tree,n=>n.type==='textarea')[0].props.value,'Add Docker');
 assert.ok(all(tree,n=>n.type===ChatMessageView).some(n=>n.props.message.sendState==='uncertain'));
});
test('confirming criteria increments the job revision without disabling refinement of the latest JD',async()=>{
 const h=harness(async()=>reply());await h.submit('Create a job');h.drafts[id].revision=2;h.drafts[id].reviewed=true;
 const card=all(h.render(),n=>n.type===ChatMessageView&&n.props.message.jobDescriptionResult)[0];
 assert.equal(card.props.actionsDisabled,false);card.props.onContinue();assert.deepEqual(h.continued,[id]);
 card.props.onRevise();assert.equal(all(h.render(),n=>n.type==='textarea')[0].props.value,'');
});
test('selected saved conversation restores without a model call; failure cannot start another job',async()=>{
 let sent=0;const ok=harness(async()=>{sent++;return reply();},undefined,conversation);ok.render();await ok.flush();
 assert.ok(all(ok.render(),n=>n.type===ChatMessageView).some(n=>n.props.message.jobReference===reference));assert.equal(sent,0);
 const fail=harness(async()=>{sent++;return reply();},async()=>{throw Error('Expired');},conversation);fail.render();await fail.flush();
 assert.equal(all(fail.render(),n=>n.type==='textarea')[0].props.disabled,true);await fail.submit('Change this role');assert.equal(sent,0);
});

test('chat publish command opens saved-job review without an interpretation or provider request',async()=>{
 let sends=0;const x=harness(async()=>{sends++;return reply();});
 await x.submit('Create a job');const tree=await x.submit('publish to Discord and LinkedIn');
 assert.equal(sends,1);
 const reviews=all(tree,n=>n.type===publishingReview.default);assert.equal(reviews.length,1);
 assert.equal(reviews[0].props.message.jobReference,reference);
 assert.equal(all(tree,n=>n.type==='textarea')[0].props.value,'');
});
test('publish without a saved draft cannot invoke inference or publication',async()=>{
 const x=harness(async()=>assert.fail('No model call'));const tree=await x.submit('/publish');
 assert.equal(all(tree,n=>n.type===publishingReview.default).length,0);
 assert.match(renderToStaticMarkup(tree),/Open a saved job draft before publishing/);
});

test('real chat publishing handlers preserve independent receipts and partial success without reposting',async()=>{
 const calls:string[]=[];
 const x=harness(async()=>reply(),undefined,undefined,async(_result,_context,job,destination)=>{
  assert.equal(job,id);calls.push(destination);
  if(destination==='telegram')throw Error('Publication unconfirmed. Check the selected destination before another attempt.');
  return {destination:'discord',status:'published',external_id:'123456789012345678'};
 });
 await x.submit('Create a synthetic job');let tree=await x.submit('/publish');
 let review=all(tree,n=>n.type===publishingReview.default)[0];
 const first=review.props.onPublish(['discord','telegram']);
 await review.props.onPublish(['discord','telegram']);await first;
 tree=x.render();review=all(tree,n=>n.type===publishingReview.default)[0];
 assert.deepEqual(calls,['discord','telegram']);
 assert.equal(review.props.message.publications.discord.status,'success');
 assert.equal(review.props.message.publications.telegram.status,'failed');
 assert.equal(review.props.message.publication.result.destination,'discord');
 const html=renderToStaticMarkup(h(publishingReview.default,review.props));
 assert.match(html,/Discord: published/);assert.match(html,/Telegram: Publication unconfirmed/);
 assert.doesNotMatch(html,/Telegram: published/);
 await review.props.onPublish(['discord','telegram']);assert.equal(calls.length,2);
});
