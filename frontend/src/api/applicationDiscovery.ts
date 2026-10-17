import {authenticatedFetch} from './session.ts';
import type {ApplicationIdentity} from './candidateComparison';
export interface DiscoveredApplication extends ApplicationIdentity {
 kind:'scored'|'unscored'|'historical_snapshot'|'unavailable';label:string;detail:string;
 evidence_revision:number|null;recorded_revisions:number[];report_available:boolean;comparison_available:boolean;
}
export interface ApplicationDiscovery {job_id:string;criteria_revision:number;applications:DiscoveredApplication[];notice:string;}
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function validDiscovery(value:unknown,job:string,revision:number):value is ApplicationDiscovery{
 const v=value as ApplicationDiscovery;
 return !!v&&v.job_id===job&&v.criteria_revision===revision&&typeof v.notice==='string'&&Array.isArray(v.applications)&&v.applications.length<=200
  &&new Set(v.applications.map(a=>`${a?.batch_id}/${a?.upload_id}`)).size===v.applications.length
  &&v.applications.every(a=>a&&a.job_id===job&&uuid.test(a.batch_id)&&uuid.test(a.upload_id)
   &&['scored','unscored','historical_snapshot','unavailable'].includes(a.kind)&&typeof a.label==='string'&&typeof a.detail==='string'
   &&typeof a.report_available==='boolean'&&typeof a.comparison_available==='boolean'
   &&(a.evidence_revision===null||Number.isInteger(a.evidence_revision)&&a.evidence_revision>=1)
   &&Array.isArray(a.recorded_revisions)&&a.recorded_revisions.length<=500&&a.recorded_revisions.every(n=>Number.isInteger(n)&&n>=1)
   &&(!a.report_available||a.evidence_revision!==null)&&(!a.comparison_available||a.report_available&&a.evidence_revision===revision));
}
export async function fetchApplications(job:string,revision:number,signal?:AbortSignal):Promise<ApplicationDiscovery>{
 if(!uuid.test(job))throw Error('Select an owned job.');
 const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
 const r=await authenticatedFetch(`${base}/api/v1/jobs/${job}/assessment-applications`,{cache:'no-store',signal});
 if(!r.ok)throw Error('Application evidence unavailable. Reload the owned job.');
 const v:unknown=await r.json();if(!validDiscovery(v,job,revision))throw Error('Application identities could not be validated.');return v;
}
