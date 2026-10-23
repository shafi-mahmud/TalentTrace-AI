import type {CandidateScore, ScoringBatch} from '../types/screening';
import type {InterviewRequest} from '../api/interviews';
import {localSchedule} from './interviewTime.ts';

export interface BookingReview {jobReference:string; request:InterviewRequest}

// Review is a snapshot of this exact selection, not authorization to bypass the server.
export function bookingReview(jobId:string, revision:number, batch:ScoringBatch, candidate:CandidateScore,
  start:string, zone:string, duration:number, acknowledged:boolean, now=Date.now()):BookingReview {
  const schedule=localSchedule(start,zone,now);
  if(batch.job_id!==jobId || batch.criteria_revision!==revision || !batch.candidates.includes(candidate) ||
    candidate.job_reference!==batch.job_reference || candidate.screening_decision!=='eligible' ||
    (candidate.status!=='scored' && (!acknowledged || !['uncertain_evidence','missing_dimension_criteria'].includes(candidate.reason ?? ''))) || !schedule.utc ||
    !Number.isInteger(duration) || duration<15 || duration>180) throw new Error('Booking review unavailable');
  return {jobReference:batch.job_reference,request:{batch_id:batch.batch_id,upload_id:candidate.upload_id,
    criteria_revision:revision,scoring_version:batch.scoring_version,selection_confirmed:true,
    confirm_eligible_unscored:candidate.status!=='scored' && acknowledged,
    scheduled_at:schedule.utc,timezone:zone,duration_minutes:duration}};
}

export function scheduleSummary(start:string, zone:string, duration:number):string {
  const format=new Intl.DateTimeFormat('en',{dateStyle:'medium',timeStyle:'short',timeZone:zone});
  return `Start: ${format.format(new Date(start))} · End: ${format.format(new Date(Date.parse(start)+duration*60000))} (${zone}) · ${duration} minutes`;
}
