import {authenticatedFetch} from './session.ts';
export type BulkCandidate={batch_id:string;upload_id:string;recipient_mask:string|null;reason:string|null;status?:string};
export type BulkOperation={operation_id:string;job_id:string;status:'preview'|'running'|'completed'|'partial'|'review_required';criteria_revision:number;expires_at:string;preview:{eligible_scored:number;validated_contacts:number;sendable:number;exclusions:Record<string,number>;candidates:BulkCandidate[];can_send:boolean;maximum_recipients:number};counts:Record<string,number>;outcomes:BulkCandidate[]};
const uuid=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
const count=(v:unknown)=>Number.isInteger(v)&&Number(v)>=0&&Number(v)<=100;
export function validBulkOperation(v:unknown,job:string,revision:number):v is BulkOperation{
 if(!v||typeof v!=='object')return false;const x=v as BulkOperation,p=x.preview;
 const reasons=['stale_criteria','incomplete_result','invalid_result','ineligible','not_scored','missing_or_ambiguous_contact','not_allowlisted','already_scheduled','already_invited','duplicate_recipient'];
 const candidate=(c:BulkCandidate)=>c&&uuid.test(c.batch_id)&&uuid.test(c.upload_id)&&(c.recipient_mask===null||typeof c.recipient_mask==='string'&&c.recipient_mask.length<=254&&c.recipient_mask.includes('***@'))&&(c.reason===null||typeof c.reason==='string'&&reasons.includes(c.reason));
 return uuid.test(x.operation_id)&&x.job_id===job&&x.criteria_revision===revision&&['preview','running','completed','partial','review_required'].includes(x.status)&&typeof x.expires_at==='string'&&Number.isFinite(Date.parse(x.expires_at))&&!!p&&count(p.eligible_scored)&&count(p.validated_contacts)&&count(p.sendable)&&p.maximum_recipients===10&&typeof p.can_send==='boolean'&&(!p.can_send||p.sendable>0&&p.sendable<=10)&&!!p.exclusions&&Object.values(p.exclusions).every(count)&&Array.isArray(p.candidates)&&p.candidates.length<=100&&p.candidates.every(candidate)&&!!x.counts&&['accepted','failed','uncertain','skipped','pending'].every(k=>count(x.counts[k]))&&Array.isArray(x.outcomes)&&x.outcomes.length<=10&&x.outcomes.every(c=>candidate(c)&&['accepted','failed','uncertain','skipped','pending'].includes(c.status??''))&&['accepted','failed','uncertain','skipped','pending'].every(k=>x.counts[k]===x.outcomes.filter(c=>c.status===k).length)&&p.sendable===p.candidates.filter(c=>c.reason===null).length;
}
export class BulkPreviewConflict extends Error {}
const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
async function request(job:string,revision:number,path:string,body?:unknown){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),body===undefined?15000:120000);
 try{const r=await authenticatedFetch(`${base}/api/v1/jobs/${job}/bulk-scheduling/${path}`,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-TalentTrace-Job-Revision':String(revision)},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:controller.signal});if(r.status===409)throw new BulkPreviewConflict('Refresh the preview before confirming.');if(!r.ok)throw new Error('Request unavailable. Refresh the preview or check the saved operation status.');const value:unknown=await r.json();if(!validBulkOperation(value,job,revision))throw new Error('Operation response could not be validated.');return value;}finally{clearTimeout(timer);}
}
export const previewInvitations=(job:string,revision:number)=>request(job,revision,'preview',{});
export const confirmInvitations=(job:string,revision:number,id:string)=>request(job,revision,'send',{operation_id:id,confirmed:true});
export const checkInvitationStatus=(job:string,revision:number,id:string)=>request(job,revision,`operations/${id}`);
