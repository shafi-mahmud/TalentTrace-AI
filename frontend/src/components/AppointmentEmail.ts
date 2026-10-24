import {createElement as h,useEffect,useRef,useState} from 'react';
import type {Interview} from '../api/interviews.ts';
import {emailLabels,emailStatus,previewEmail,sendEmail} from '../api/appointmentEmail.ts';
import type {EmailPreview,EmailStatus} from '../api/appointmentEmail.ts';

export default function AppointmentEmail({interview}:{interview:Interview}){
 const [open,setOpen]=useState(false),[recipient,setRecipient]=useState(''),[review,setReview]=useState<EmailPreview|null>(null);
 const [confirmed,setConfirmed]=useState(false),[status,setStatus]=useState<EmailStatus|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const pending=useRef(false),attempted=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 const locked=attempted.current || (status!==null && !['none','not_configured'].includes(status));
 async function load(){if(pending.current)return;pending.current=true;setBusy(true);setError('');
  try{const v=await emailStatus(interview.job_id,interview.id);if(alive.current){setStatus(v);setOpen(true);setReview(null);setConfirmed(false);}}
  catch{if(alive.current)setError('Delivery status unavailable. Verify the saved appointment before proceeding.');}
  finally{pending.current=false;if(alive.current)setBusy(false);}}
 async function preview(){if(pending.current||locked||!recipient||status!=='none')return;pending.current=true;setBusy(true);setError('');
  try{const v=await previewEmail(interview.job_id,interview.id,recipient);if(alive.current){setReview(v);setConfirmed(false);}}
  catch(e){if(alive.current){setReview(null);setError(e instanceof Error?e.message:'Preview unavailable.');}}
  finally{pending.current=false;if(alive.current)setBusy(false);}}
 async function send(){if(pending.current||locked||!review||!confirmed)return;pending.current=true;attempted.current=true;setBusy(true);setError('');
  const v=await sendEmail(interview.job_id,interview.id,recipient,review);
  if(alive.current){setStatus(v);setReview(null);setConfirmed(false);setRecipient('');setBusy(false);}pending.current=false;
 }
 return h('section',{'aria-label':'Appointment confirmation email',className:'session-confirmation'},
  h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>void load()},open?'Reload delivery status':'Review appointment email'),
  error && h('p',{role:'alert'},error),
  open && h('div',null,
   h('p',null,'Appointment confirmation only. No joining link or interview access is included. Arrange joining access separately.'),
   busy && h('p',{role:'status'},attempted.current?'Sending…':'Loading…'),
   !busy && status && h('p',{role:'status'},emailLabels[status]),
   status==='accepted' && h('p',null,'SMTP acceptance does not prove mailbox delivery.'),
   (locked || status==='uncertain') && h('p',null,'No resend is available. An interrupted or uncertain send requires operator reconciliation.'),
   !locked && status==='none' && h('div',null,
    h('label',null,'Approved recipient email',h('input',{type:'email',autoComplete:'off',maxLength:254,value:recipient,disabled:busy,onChange:(e:{target:{value:string}})=>{setRecipient(e.target.value);setReview(null);setConfirmed(false);}})),
    h('button',{type:'button',className:'button button-secondary',disabled:busy||!recipient,onClick:()=>void preview()},'Preview saved appointment'),
    review && h('div',{'aria-label':'Review appointment email before sending'},
     h('p',null,`Approved recipient: ${review.recipient_mask}`),
     h('p',{role:'status'},review.contact_status==='matches_recorded'?'Matches the recorded imported application contact. Google Forms respondent input does not verify mailbox ownership.':'No recorded application contact. This address was entered manually; independently verify the intended recipient.'),h('h4',null,review.subject),h('p',{style:{whiteSpace:'pre-wrap'}},review.body),
     h('label',null,h('input',{type:'checkbox',checked:confirmed,disabled:busy,onChange:(e:{target:{checked:boolean}})=>setConfirmed(e.target.checked)}),' I confirm the approved recipient and saved appointment details. This email gives no joining access.'),
     h('button',{type:'button',className:'button button-primary',disabled:busy||!confirmed,onClick:()=>void send()},busy?'Sending…':'Send appointment confirmation')))));
}
