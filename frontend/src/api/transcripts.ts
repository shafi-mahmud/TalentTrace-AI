const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const consentVersion='optional-transcript-storage-v1';
export interface TranscriptContext {candidate:boolean;jobId?:string;interviewId?:string;}
export interface StorageConfig {enabled:boolean;version:string;wording:string;}
export interface Setup {capture_id:string;interview_id:string;status:string;}
export interface PrivacyStatus {withdrawn:boolean;expired:boolean;deletion_verified:boolean;deletion_status:string;
  capture_status:string|null;persistence_outcome:string|null;retention_deadline:string|null;}
export interface Turn {id:string;capture_id:string;sequence:number;role:'recruiter'|'candidate';text:string;start_ms:number;end_ms:number;}
export interface TranscriptReview {turns:Turn[];captures:{id:string;status:string;outcome:string;summary:unknown}[];warning:string;next_offset:number|null;}
async function request(path:string,body?:unknown,version?:string) {
  const response=await fetch(base+'/api/v1'+path,{credentials:'include',cache:'no-store',
    method:body===undefined?'GET':'POST',headers:{'X-TalentTrace-Request':'1',
      ...(body===undefined?{}:{'Content-Type':'application/json'}),...(version?{'X-TalentTrace-Storage-Consent':version}:{})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok)throw Error('Transcript operation was not confirmed. Check status before repeating a request.');
  return await response.json();
}
function recruiterPath(c:TranscriptContext) {
  if(!c.jobId || !c.interviewId || !uuid.test(c.jobId) || !uuid.test(c.interviewId))throw Error('Select a saved interview first.');
  return `/jobs/${c.jobId}/interviews/${c.interviewId}`;
}
export async function storageConfig():Promise<StorageConfig> {
  const v=await request('/transcript-storage/config');
  if(typeof v?.enabled!=='boolean' || v.version!==consentVersion || typeof v.wording!=='string' || v.wording.length>5000)throw Error('Storage disclosure unavailable.');
  return v;
}
export async function prepareStorage(c:TranscriptContext):Promise<Setup> {
  const v=await request((c.candidate?'/interview-access':recruiterPath(c))+'/transcript-storage/prepare',{});
  if(!uuid.test(v?.capture_id??'') || !uuid.test(v?.interview_id??'') || typeof v.status!=='string')throw Error('Capture identity could not be validated.');
  return v;
}
export async function storageDecision(c:TranscriptContext,capture:string,decision:'accept'|'decline') {
  if(!uuid.test(capture))throw Error('Invalid capture identity.');
  return request((c.candidate?'/interview-access':recruiterPath(c))+'/transcript-storage/decision',
    {capture_id:capture,decision},decision==='accept'?consentVersion:undefined);
}
export async function privacyStatus(c:TranscriptContext):Promise<PrivacyStatus> {
  const v=await request(c.candidate?'/interview-transcripts/privacy/status':recruiterPath(c)+'/transcript-storage/status');
  if(!v || ['withdrawn','expired','deletion_verified'].some(k=>typeof v[k]!=='boolean')
    || !['none','pending','failed','deleted'].includes(v.deletion_status))throw Error('Privacy status could not be validated.');
  return v;
}
export async function withdrawStorage(c:TranscriptContext) {
  return request(c.candidate?'/interview-transcripts/privacy/withdraw':recruiterPath(c)+'/transcript-storage/withdraw',{});
}
export function isTranscriptReview(v:any):v is TranscriptReview {
  return !!v && Array.isArray(v.turns) && v.turns.length<=200 && v.turns.every((r:any)=>
    uuid.test(r?.id??'') && uuid.test(r.capture_id??'') && Number.isInteger(r.sequence) && r.sequence>0
    && ['recruiter','candidate'].includes(r.role) && typeof r.text==='string' && r.text.length>0 && r.text.length<=1000
    && !/[\u0000-\u001f\u007f-\u009f]/.test(r.text) && Number.isInteger(r.start_ms) && r.start_ms>=0 && Number.isInteger(r.end_ms) && r.end_ms>=r.start_ms)
    && Array.isArray(v.captures) && v.captures.length<=100 && v.captures.every((c:any)=>uuid.test(c?.id??'')
      && ['active','completed','interrupted'].includes(c.status) && ['pending','saved','partial','failed'].includes(c.outcome))
    && typeof v.warning==='string' && v.warning.length<=1000 && (v.next_offset===null || Number.isInteger(v.next_offset)&&v.next_offset>=0);
}
export async function reviewTranscript(c:TranscriptContext,offset=0):Promise<TranscriptReview> {
  if(c.candidate)throw Error('Transcript review is recruiter-only.');
  const v=await request(recruiterPath(c)+`/transcript?offset=${offset}`);
  if(!isTranscriptReview(v))throw Error('Transcript response could not be validated.');
  return v;
}
