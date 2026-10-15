export interface Caption {kind:"caption";role:"recruiter"|"candidate";sequence:number;start:number;end:number;text:string}
export interface DrainCounts {accepted_frames:number;accepted_samples:number;processed_samples:number;caption_events:number;captured_samples:number|null}
export interface Finalization {kind:"finalized";outcome:"drained"|"partial"|"failed";roles:Record<"recruiter"|"candidate",DrainCounts>}
export function isFinalization(value:unknown, duration=120):value is Finalization {
  if(!value || typeof value!=="object" || !Number.isInteger(duration) || duration<120 || duration>300)return false;
  const v=value as Finalization;
  if(Object.keys(v).length!==3 || v.kind!=="finalized" || !["drained","partial","failed"].includes(v.outcome)
    || !v.roles || Object.keys(v.roles).sort().join()!=="candidate,recruiter")return false;
  return Object.values(v.roles).every(c=>c && Object.keys(c).sort().join()==="accepted_frames,accepted_samples,caption_events,captured_samples,processed_samples"
    && [c.accepted_frames,c.accepted_samples,c.processed_samples,c.caption_events].every(n=>Number.isInteger(n)&&n>=0)
    && c.accepted_frames<=duration*10+1 && c.accepted_samples<=duration*16000 && c.processed_samples<=c.accepted_samples
    && c.caption_events<=Math.max(120,Math.floor(duration/2))
    && (c.captured_samples===null || (Number.isInteger(c.captured_samples)&&c.captured_samples>=c.accepted_samples&&c.captured_samples<=duration*16000))
    && (v.outcome!=="drained" || (c.processed_samples===c.accepted_samples&&c.captured_samples!==null)));
}
export function isCaption(v:unknown, durationSeconds=120):v is Caption {
  if(!Number.isInteger(durationSeconds) || durationSeconds<1 || durationSeconds>300)return false;
  if(!v || typeof v!=="object")return false;
  const c=v as Caption;
  return Object.keys(c).length===6 && c.kind==="caption" && ["recruiter","candidate"].includes(c.role)
    && Number.isInteger(c.sequence) && c.sequence>0 && c.sequence<=Math.max(120,Math.floor(durationSeconds/2))
    && Number.isFinite(c.start) && c.start>=0 && Number.isFinite(c.end) && c.end>=c.start && c.end<=durationSeconds
    && typeof c.text==="string" && c.text.length>0 && c.text.length<=1000 && !/[\x00-\x1f\x7f-\x9f]/.test(c.text);
}
export function captionUrl(candidate:boolean,jobId?:string,interviewId?:string):string {
  const url=new URL(candidate?"/api/v1/interview-access/captions":`/api/v1/jobs/${jobId}/interviews/${interviewId}/captions`,window.location.origin);
  url.protocol=url.protocol==="https:"?"wss:":"ws:";return url.href;
}
