import {authenticatedFetch} from './session.ts';
export type Position='alignment'|'mixed'|'insufficient';
export type Scope='cv_only'|'cv_interview';
export type Reason='supported_requirement'|'documented_concern'|'uncertain_finding'|'missing_evidence';
export interface EvidenceReference {criterion_id:string;kind:'cv'|'interview'|'gap';reason:Reason;qa_id:string|null;dimension:string|null;}
export interface ConfirmationView {
 enabled:boolean;state:'pending'|'stale'|'restricted'|'confirmed';version:number;evidence_token:string|null;
 position:Position|null;scope:Scope|null;requirement_ids:string[];references:EvidenceReference[];
 reviewer_id:string|null;confirmed_at:string|null;expires_at:string|null;
}
export const positionLabels:Record<Position,string>={alignment:'Evidence supports alignment within reviewed scope.',mixed:'Mixed evidence; specific concerns require review.',insufficient:'Insufficient evidence to form a suitability position.'};
export const reasonLabels:Record<Reason,string>={supported_requirement:'Supported requirement',documented_concern:'Documented concern',uncertain_finding:'Uncertain finding requires verification',missing_evidence:'Missing or unassessed evidence'};
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function validConfirmation(v:unknown):v is ConfirmationView{
 const c=v as ConfirmationView;
 if(!c||typeof c.enabled!=='boolean'||!['pending','stale','restricted','confirmed'].includes(c.state)||!Number.isInteger(c.version)||c.version<0
  ||!(c.evidence_token===null||typeof c.evidence_token==='string'&&/^[0-9a-f]{64}$/.test(c.evidence_token))
  ||!Array.isArray(c.requirement_ids)||c.requirement_ids.length>50||!Array.isArray(c.references)||c.references.length>100)return false;
 if(c.state!=='confirmed')return c.position===null&&c.scope===null&&c.reviewer_id===null&&c.confirmed_at===null&&c.expires_at===null&&c.references.length===0&&c.requirement_ids.length===0;
 if(!c.enabled||!Object.hasOwn(positionLabels,c.position??'')||!['cv_only','cv_interview'].includes(c.scope??'')||!uuid.test(c.reviewer_id??'')
  ||!c.confirmed_at||!c.expires_at||!Number.isFinite(Date.parse(c.confirmed_at))||Date.parse(c.expires_at)<=Date.now()||!Number.isFinite(Date.parse(c.expires_at)))return false;
 return c.requirement_ids.length>0&&new Set(c.requirement_ids).size===c.requirement_ids.length&&c.requirement_ids.every(id=>typeof id==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id))
  &&c.references.length>0&&c.references.every(r=>r&&c.requirement_ids.includes(r.criterion_id)&&Object.hasOwn(reasonLabels,r.reason)
   &&['cv','interview','gap'].includes(r.kind)&&(r.kind==='interview'?uuid.test(r.qa_id??'')&&['relevance','technical_accuracy','completeness','articulation'].includes(r.dimension??''):r.qa_id===null&&r.dimension===null));
}
export async function saveConfirmation(job:string,batch:string,upload:string,body:{expected_version:number;evidence_token:string;position:Position;scope:Scope;requirement_ids:string[];references:EvidenceReference[]},signal?:AbortSignal){
 if(![job,batch,upload].every(id=>uuid.test(id)))throw Error('Select an exact saved application.');
 const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
 const response=await authenticatedFetch(`${base}/api/v1/jobs/${job}/batches/${batch}/candidates/${upload}/assessment/confirmation`,{
  method:'PUT',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify(body),signal});
 if(!response.ok)throw Error('Confirmation outcome was not verified. Refresh the report before explicitly reconciling; do not retry automatically.');
 const value:unknown=await response.json();if(!validConfirmation(value))throw Error('Confirmation outcome was not verified. Refresh the report.');return value;
}
