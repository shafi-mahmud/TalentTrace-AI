import {createElement as h,useLayoutEffect,useRef,useState} from 'react';
import {previewInvitations,confirmInvitations,checkInvitationStatus,BulkPreviewConflict} from '../api/bulkScheduling.ts';
import type {BulkOperation} from '../api/bulkScheduling.ts';
export function canConfirm(operation:BulkOperation|null,busy:boolean,uncertain:boolean){return !!operation&&operation.status==='preview'&&operation.preview.can_send&&!busy&&!uncertain;}
function retained(key:string){try{return sessionStorage.getItem(key);}catch{return null;}}
export function BulkSummary({operation}:{operation:BulkOperation}){
 const p=operation.preview;
 return h('div',null,h('p',null,`Eligible scored: ${p.eligible_scored} · Validated original contacts: ${p.validated_contacts} · Unique sendable recipients: ${p.sendable}`),h('ul',null,...Object.entries(p.exclusions).map(([reason,n])=>h('li',{key:reason},`${reason.replaceAll('_',' ')}: ${n}`))),h('p',null,`Operation: ${operation.status}`),operation.status!=='preview'&&h('p',null,`Accepted: ${operation.counts.accepted} · Failed: ${operation.counts.failed} · Uncertain: ${operation.counts.uncertain} · Skipped: ${operation.counts.skipped} · Pending: ${operation.counts.pending}`),h('ul',null,...(operation.status==='preview'?p.candidates:operation.outcomes).map(c=>h('li',{key:c.batch_id+c.upload_id},`Candidate ${c.upload_id.slice(0,8)} · ${c.recipient_mask??'Contact unavailable'} · ${c.status??c.reason??'Ready for approval'}`))),h('p',null,'Accepted means SMTP acceptance, not confirmed mailbox delivery. Uncertain attempts are never automatically resent.'));
}
export default function BulkScheduling({jobId,revision}:{jobId:string;revision:number}){
 const [operation,setOperation]=useState<BulkOperation|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[uncertain,setUncertain]=useState(false);
 const pending=useRef(false),generation=useRef(0);const key=`talenttrace-bulk:${jobId}:${revision}`;
 useLayoutEffect(()=>{const n=++generation.current;pending.current=false;setOperation(null);setError('');setBusy(false);setUncertain(false);const id=retained(key);if(id){pending.current=true;setBusy(true);void checkInvitationStatus(jobId,revision,id).then(v=>{if(n===generation.current)setOperation(v);}).catch(()=>{if(n===generation.current){setUncertain(true);setError('Saved operation could not be checked. Do not send again until its status is verified.');}}).finally(()=>{if(n===generation.current){pending.current=false;setBusy(false);}});}return()=>{generation.current++;};},[jobId,revision]);
 async function act(kind:'preview'|'send'|'status'){
  if(pending.current)return;pending.current=true;setBusy(true);setError('');const n=generation.current;
  const id=operation?.operation_id??retained(key);
  try{
   let value:BulkOperation;
   if(kind==='preview')value=await previewInvitations(jobId,revision);
   else if(!id)throw new Error('No saved operation. Prepare a preview first.');
   else value=await(kind==='send'?confirmInvitations(jobId,revision,id):checkInvitationStatus(jobId,revision,id));
   if(n===generation.current){setOperation(value);sessionStorage.setItem(key,value.operation_id);setUncertain(false);}
  }catch(e){
   if(n===generation.current&&e instanceof BulkPreviewConflict){setError('Preview changed or sending is unavailable. Refresh the preview and review it again.');setOperation(v=>v?{...v,preview:{...v.preview,can_send:false}}:v);setUncertain(false);}
   else if(n===generation.current){setError(kind==='send'?'Delivery outcome is not confirmed. Check the saved operation status; do not send again.':'Request unavailable. Check authentication, criteria and saved operation status.');if(kind==='send')setUncertain(true);}
  }finally{if(n===generation.current){pending.current=false;setBusy(false);}}
 }
 return h('section',{className:'card','aria-label':'Bulk scheduling invitations'},h('h2',null,'Scheduling invitations for eligible candidates'),h('p',null,'Use original application contacts. Previewing sends no email; confirmation approves the complete displayed cohort.'),h('button',{type:'button',disabled:busy||uncertain||operation?.status==='running',onClick:()=>void act('preview')},'Preview Invitations to All Eligible Candidates'),operation&&h(BulkSummary,{operation}),operation?.status==='preview'&&!operation.preview.can_send&&h('p',null,'Sending unavailable: no approved unique recipients, email disabled, or recipient limit exceeded.'),operation?.status==='preview'&&h('button',{type:'button',disabled:!canConfirm(operation,busy,uncertain),onClick:()=>void act('send')},busy?'Processing…':'Confirm & Send Invitations'),h('button',{type:'button',disabled:busy,onClick:()=>void act('status')},'Check saved operation status'),error&&h('p',{role:'alert'},error),operation?.status==='review_required'&&h('p',{role:'alert'},'Operator review required. Do not retry delivery.'));
}
