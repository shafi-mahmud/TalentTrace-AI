import {authenticatedFetch} from './session.ts';
export type EmailStatus = 'none'|'not_configured'|'accepted'|'failed'|'uncertain';
export interface EmailPreview {subject:string;body:string;review_digest:string;}
const base=(import.meta.env?.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');
const path=(job:string,id:string)=>`${base}/api/v1/jobs/${job}/interviews/${id}/appointment-email`;
export const emailLabels:Record<EmailStatus,string>={none:'No delivery attempt',not_configured:'Not configured',accepted:'Accepted by SMTP',failed:'Failed',uncertain:'Delivery uncertain'};
function failure(status:number):Error {return new Error(status===503?'Not configured':status===422?'Enter an explicitly approved recipient.':'Review unavailable. Reload delivery status and verify the saved appointment.');}
export async function emailStatus(job:string,id:string):Promise<EmailStatus>{
 const r=await authenticatedFetch(path(job,id));if(!r.ok)throw failure(r.status);
 const v=await r.json().catch(()=>null);if(!v || Object.keys(v).length!==1 || !Object.hasOwn(emailLabels,v.email_status))throw Error('Delivery status unavailable.');
 return v.email_status;
}
export async function previewEmail(job:string,id:string,recipient:string):Promise<EmailPreview>{
 const r=await authenticatedFetch(path(job,id)+'/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient})}).catch(()=>{throw Error('Preview unavailable.');});
 if(!r.ok)throw failure(r.status);const v=await r.json().catch(()=>null);
 if(!v || Object.keys(v).length!==3 || typeof v.subject!=='string' || v.subject.length>160 || typeof v.body!=='string' || v.body.length>2000 || !/^[a-f0-9]{64}$/.test(v.review_digest))throw Error('Preview unavailable.');
 return v;
}
export async function sendEmail(job:string,id:string,recipient:string,review:EmailPreview):Promise<EmailStatus>{
 try{
  const r=await authenticatedFetch(path(job,id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient,review_digest:review.review_digest,confirmed:true})});
  if(!r.ok) return r.status===503?'not_configured':'uncertain';
  const v=await r.json().catch(()=>null);return v && Object.keys(v).length===1 && ['accepted','failed','uncertain'].includes(v.email_status)?v.email_status:'uncertain';
 }catch{return 'uncertain';}
}
