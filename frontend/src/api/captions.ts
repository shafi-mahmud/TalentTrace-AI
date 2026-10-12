export interface Caption {kind:"caption";role:"recruiter"|"candidate";sequence:number;start:number;end:number;text:string}
export function isCaption(v:unknown):v is Caption {
  if(!v || typeof v!=="object")return false;
  const c=v as Caption;
  return Object.keys(c).length===6 && c.kind==="caption" && ["recruiter","candidate"].includes(c.role)
    && Number.isInteger(c.sequence) && c.sequence>0 && c.sequence<=120
    && Number.isFinite(c.start) && c.start>=0 && Number.isFinite(c.end) && c.end>=c.start && c.end<=120
    && typeof c.text==="string" && c.text.length>0 && c.text.length<=1000 && !/[\x00-\x1f\x7f-\x9f]/.test(c.text);
}
export function captionUrl(candidate:boolean,jobId?:string,interviewId?:string):string {
  const url=new URL(candidate?"/api/v1/interview-access/captions":`/api/v1/jobs/${jobId}/interviews/${interviewId}/captions`,window.location.origin);
  url.protocol=url.protocol==="https:"?"wss:":"ws:";return url.href;
}
