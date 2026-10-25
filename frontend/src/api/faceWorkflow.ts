import {authenticatedFetch} from './session.ts';
export interface FaceState {state:string;retention_seconds?:number;run_id?:string;expires_at?:number;wording?:string;version?:string;interview_id?:string;withdrawal_receipt?:string;viva_authorized?:boolean;}
export interface FaceResult {similarity:number;provisional:true;human_review_required:true;identity_verified:false;liveness_checked:false;synthetic_only:true;decision:'no_automated_decision';}
export function validResult(v:any):v is FaceResult{return !!v&&Object.keys(v).length===7&&typeof v.similarity==='number'&&Number.isFinite(v.similarity)&&v.similarity>=-1&&v.similarity<=1&&v.provisional===true&&v.human_review_required===true&&v.identity_verified===false&&v.liveness_checked===false&&v.synthetic_only===true&&v.decision==='no_automated_decision';}
export async function faceRequest(path:string,body?:unknown):Promise<any>{
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
 try{
  const response=await authenticatedFetch('/api/v1/'+path,{signal:controller.signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  if(response.status===404&&body===undefined)return null;
  if(!response.ok)throw Error('Synthetic reference unavailable. Refresh before retrying.');
  const value=await response.json();
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error();
  return value;
 }catch{throw Error('Synthetic reference unavailable. Refresh before retrying.');}finally{clearTimeout(timer);}
}
