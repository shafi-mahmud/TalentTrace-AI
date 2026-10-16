import {authenticatedFetch} from './session.ts';
import {validReport} from './consolidatedAssessment.ts';
import type {ConsolidatedReport} from './consolidatedAssessment';
export interface ApplicationIdentity {job_id:string;batch_id:string;upload_id:string;}
export interface Comparison {
 version:'f6-comparison-1';job_id:string;criteria_revision:number;
 reports:[ConsolidatedReport,ConsolidatedReport];review_required:true;notice:string;
}
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function sameApplication(a:ApplicationIdentity,b:ApplicationIdentity){return a.job_id===b.job_id&&a.batch_id===b.batch_id&&a.upload_id===b.upload_id;}
export function validSelections(job:string,selections:ApplicationIdentity[]):boolean{
 return selections.length===2&&uuid.test(job)&&selections.every(a=>a.job_id===job&&uuid.test(a.batch_id)&&uuid.test(a.upload_id))&&!sameApplication(selections[0],selections[1]);
}
export function validComparison(value:unknown,job:string,revision:number,selections:ApplicationIdentity[]):value is Comparison{
 const v=value as Comparison;
 return validSelections(job,selections)&&!!v&&v.version==='f6-comparison-1'&&v.job_id===job&&v.criteria_revision===revision
  &&v.review_required===true&&typeof v.notice==='string'&&Array.isArray(v.reports)&&v.reports.length===2
  &&v.reports.every((r,i)=>validReport(r,job,selections[i].batch_id,selections[i].upload_id)&&r.criteria_revision===revision)
  &&(['skill','experience','education'] as const).every(d=>v.reports[0].cv.weights[d]===v.reports[1].cv.weights[d]);
}
export async function fetchComparison(job:string,revision:number,selections:ApplicationIdentity[],signal?:AbortSignal):Promise<Comparison>{
 if(!validSelections(job,selections))throw Error('Select two distinct applications from the same job.');
 const [a,b]=selections;
 const query=new URLSearchParams({left_batch:a.batch_id,left_upload:a.upload_id,right_batch:b.batch_id,right_upload:b.upload_id});
 const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
 const r=await authenticatedFetch(`${base}/api/v1/jobs/${job}/assessment-comparison?${query}`,{cache:'no-store',signal});
 if(!r.ok)throw Error('Comparison unavailable. Reload the owned job and select current saved applications.');
 const value:unknown=await r.json();
 if(!validComparison(value,job,revision,selections))throw Error('Comparison associations could not be validated.');
 return value;
}
