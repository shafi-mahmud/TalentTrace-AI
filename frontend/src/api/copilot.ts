// Separate transient processing consent. No transcript submission API exists.
const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const version='local-copilot-v1';
export interface Context {candidate:boolean;jobId?:string;interviewId?:string;}
export interface Suggestion {id:string;question:string;requirement:string;reason:string;provisional:true;}
export interface Status {enabled:boolean;live_connected:boolean;version:string;wording:string;
  status:'unavailable'|'withdrawn'|'authorized'|'awaiting_consent';run_id:string|null;epoch:number;
  recruiter_consented:boolean;candidate_consented:boolean;expires_in_ms:number;suggestion?:Suggestion|null;processing?:string;}
export class ResponseFence {
  private generation=0;
  next(){return ++this.generation;}
  accepts(value:number){return value===this.generation;}
  clear(){this.generation++;}
}
function path(c:Context){
  if(c.candidate)return '/interview-access/copilot';
  if(!uuid.test(c.jobId??'')||!uuid.test(c.interviewId??''))throw Error('Select an authorized interview.');
  return `/jobs/${c.jobId}/interviews/${c.interviewId}/copilot`;
}
async function request(path:string,body?:unknown){
  const r=await fetch(base+'/api/v1'+path,{credentials:'include',cache:'no-store',signal:AbortSignal.timeout(8000),method:body===undefined?'GET':'POST',
    headers:{'X-TalentTrace-Request':'1',...(body===undefined?{}:{'Content-Type':'application/json'})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!r.ok)throw Error('Assistant unavailable. Check status before another action; no automatic retry was sent.');
  return r.json();
}
export function validStatus(v:any,candidate:boolean):v is Status {
  const text=(s:any,n:number)=>typeof s==='string'&&s.length<=n&&!/[\u0000-\u001f\u007f-\u009f]/.test(s);
  return !!v&&v.enabled===true&&typeof v.live_connected==='boolean'&&v.version===version&&text(v.wording,1500)
    &&['unavailable','withdrawn','authorized','awaiting_consent'].includes(v.status)
    &&(v.run_id===null||uuid.test(v.run_id))&&Number.isInteger(v.epoch)&&v.epoch>=0
    &&Number.isInteger(v.expires_in_ms)&&v.expires_in_ms>=0&&v.expires_in_ms<=120000
    &&typeof v.recruiter_consented==='boolean'&&typeof v.candidate_consented==='boolean'
    &&(!candidate||(!('suggestion' in v)&&!('processing' in v)&&!('exploration' in v)))
    &&(v.suggestion===undefined||v.suggestion===null||(!candidate&&v.status==='authorized'
       &&v.recruiter_consented&&v.candidate_consented&&v.suggestion.provisional===true
       &&/^[a-f0-9]{64}$/.test(v.suggestion.id)&&text(v.suggestion.question,700)
       &&text(v.suggestion.requirement,500)&&text(v.suggestion.reason,500)));
}
function checked(v:any,c:Context){if(!validStatus(v,c.candidate))throw Error('Assistant response unavailable.');return v;}
export async function config(){
  const v=await request('/interview-copilot/config');
  if(typeof v?.enabled!=='boolean'||typeof v.live_connected!=='boolean'||v.version!==version||typeof v.wording!=='string'||v.wording.length>1500||(v.synthetic_cloud!==undefined&&typeof v.synthetic_cloud!=='boolean'))throw Error('Assistant configuration unavailable.');
  return v as {enabled:boolean;live_connected:boolean;version:string;wording:string;live_enabled?:boolean;synthetic_cloud?:boolean};
}
export async function status(c:Context){return checked(await request(path(c)),c);}
export async function prepare(c:Context){if(c.candidate)throw Error('Recruiter only.');return checked(await request(path(c)+'/prepare',{}),c);}
export async function decide(c:Context,s:Status,decision:'accept'|'decline'|'withdraw'){
  if(!s.run_id||!uuid.test(s.run_id)||s.epoch<1)throw Error('Check current assistant status.');
  return checked(await request(path(c)+'/consent',{run_id:s.run_id,epoch:s.epoch,version,decision}),c);
}
export async function dismiss(c:Context,s:Status){
  if(c.candidate||!s.suggestion||!s.run_id)throw Error('Recruiter suggestion required.');
  return checked(await request(path(c)+'/dismiss',{run_id:s.run_id,epoch:s.epoch,suggestion_id:s.suggestion.id}),c);
}
