import {authenticatedFetch} from './session.ts';
import {isAnalysisOperation} from './interviewAnalysis.ts';
import type {AnalysisResult} from './interviewAnalysis';
import type {CandidateScore} from '../types/screening';
import {validSavedBatches} from './savedScoreValidation.ts';

export const evidenceStates=['available','not_scheduled','disabled','withdrawn','expired','deleted','stale','missing_analysis','pending','unavailable','ambiguous'] as const;
export type EvidenceState=typeof evidenceStates[number];
export interface ConsolidatedReport {
 version:'f6-increment-1';job_id:string;job_title:string;job_reference:string;batch_id:string;upload_id:string;
 criteria_revision:number;cv_source:'current_saved_score'|'interview_selection_snapshot';cv:CandidateScore;
 interview:{state:EvidenceState;interview_id:string|null;operation_id:string|null;rubric_version:string|null;retention_deadline:string|null;warning:string|null;
 pairs:AnalysisResult['pairs'];requirements:AnalysisResult['requirements'];assessment:AnalysisResult['assessment']|null;
 references:AnalysisResult['technical_references'];turns:AnalysisResult['turns']};review_required:true;notice:string;
}
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function validReport(value:unknown,job:string,batch:string,upload:string):value is ConsolidatedReport {
 const r=value as ConsolidatedReport;
 if(!r||r.version!=='f6-increment-1'||r.job_id!==job||r.batch_id!==batch||r.upload_id!==upload||r.cv?.upload_id!==upload
  ||typeof r.job_title!=='string'||r.job_title.length>120||!Number.isInteger(r.criteria_revision)||r.criteria_revision<1
  ||r.review_required!==true||typeof r.notice!=='string'||!['current_saved_score','interview_selection_snapshot'].includes(r.cv_source))return false;
 if(!validSavedBatches([{job_id:job,job_reference:r.job_reference,batch_id:batch,criteria_revision:r.criteria_revision,
  scoring_version:'f2-coverage-v1',weights:r.cv.weights,candidates:[r.cv],ranking:[]}],job,r.criteria_revision))return false;
 const i=r.interview;
 if(!i||!evidenceStates.includes(i.state)||!(i.interview_id===null||uuid.test(i.interview_id)))return false;
 if(i.state!=='available')return i.operation_id===null&&i.assessment===null&&i.rubric_version===null&&i.retention_deadline===null&&i.warning===null
  &&[i.pairs,i.requirements,i.references,i.turns].every(a=>Array.isArray(a)&&a.length===0);
 if(!i.interview_id||!i.assessment||typeof i.warning!=='string'||typeof i.retention_deadline!=='string'||!Number.isFinite(Date.parse(i.retention_deadline))||Date.parse(i.retention_deadline)<=Date.now())return false;
 return isAnalysisOperation({operation_id:i.operation_id,status:'completed',persistence:'postgresql_privacy_bound',attempt:1,
  result:{provider:'persisted',model:'persisted',rubric_version:i.rubric_version,advisory:true,scope:'accepted_audio_only',asr_review:'unverified',
   warning:i.warning,pairs:i.pairs,requirements:i.requirements,assessment:i.assessment,technical_references:i.references,
   turns:i.turns,strengths:[],gaps:[],unpaired_turn_ids:[]}});
}
export async function fetchReport(job:string,batch:string,upload:string,signal?:AbortSignal):Promise<ConsolidatedReport>{
 if(![job,batch,upload].every(v=>uuid.test(v)))throw Error('Select a saved candidate.');
 const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
 const response=await authenticatedFetch(`${base}/api/v1/jobs/${job}/batches/${batch}/candidates/${upload}/assessment`,{cache:'no-store',signal});
 if(!response.ok)throw Error('Candidate assessment unavailable. Sign in and reload the saved job.');
 const value:unknown=await response.json();
 if(!validReport(value,job,batch,upload))throw Error('Saved assessment associations could not be validated.');
 return value;
}
