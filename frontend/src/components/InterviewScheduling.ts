import ConsolidatedAssessment from './ConsolidatedAssessment.ts';
import { createElement as h, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createInterview, listInterviews } from "../api/interviews.ts";
import { localSchedule, timezoneOptions } from "./interviewTime.ts";
import { bookingReview, scheduleSummary } from "./schedulingReview.ts";
import type { BookingReview } from "./schedulingReview.ts";
import type { Interview } from "../api/interviews.ts";
import type { CandidateScore, ScoringBatch } from "../types/screening";

export function ScheduleForm({candidate, start, zone, duration, confirmed, busy, alreadyScheduled, onStart, onZone, onDuration, onConfirmed, onSubmit, review, finalConfirmed=false, onFinalConfirmed=()=>{}, onEdit=()=>{}}: {
  review?: BookingReview|null; finalConfirmed?:boolean; onFinalConfirmed?:(v:boolean)=>void; onEdit?:()=>void;
  candidate: CandidateScore; start: string; zone: string; duration: number; confirmed: boolean; busy: boolean; alreadyScheduled: boolean;
  onStart: (v: string) => void; onZone: (v: string) => void; onDuration: (v: number) => void; onConfirmed: (v: boolean) => void; onSubmit: (e: FormEvent) => void;
}) {
  const unscored = candidate.status !== "scored";
  const preview = start ? localSchedule(start, zone) : null;
  return h("form", {onSubmit}, h("p", null, `Candidate reference: ${candidate.upload_id}`),
    h("p", {className:"helper-text"}, "You select this candidate. Scheduling does not change screening or hiring decisions. No meeting link or notification is created."),
    unscored && h("p", {role:"status", className:"error-banner"}, "Eligible but not scored. Review the missing or uncertain weighted evidence before selection."),
    h("fieldset", {disabled:busy || alreadyScheduled || !!review},
      h("legend", null, "Initial interview"),
      h("label", {htmlFor:"interview-start"}, "Local interview date and time"),
      h("input", {id:"interview-start",type:"datetime-local",value:start,required:true,onChange:(e:{target:{value:string}})=>onStart(e.target.value)}),
      h("label", {htmlFor:"interview-zone"}, "Interview timezone (IANA)"),
      h("select", {id:"interview-zone",value:zone,required:true,onChange:(e:{target:{value:string}})=>onZone(e.target.value)},
        ...timezoneOptions(zone).map(value=>h("option",{key:value,value},value))),
      h("p", {className:"helper-text"}, "Enter the time in the selected timezone. Review the start and end before confirming. Booking sends no invitation or email."),
      preview && h("p", {role:"status",className:"helper-text"}, preview.error ?? `Local: ${start.replace("T", " ")} (${zone}) · UTC: ${preview.utc}`),
      h("label", {htmlFor:"interview-duration"}, "Duration (minutes)"),
      h("input", {id:"interview-duration",type:"number",value:Number.isFinite(duration)?duration:"",min:15,max:180,step:1,required:true,onChange:(e:{target:{value:string}})=>onDuration(e.target.value === ""?NaN:Number(e.target.value))}),
      unscored && h("label", null, h("input", {type:"checkbox",checked:confirmed,onChange:(e:{target:{checked:boolean}})=>onConfirmed(e.target.checked)}), " I reviewed the uncertainty and explicitly select this eligible, unscored candidate."),
      h("button", {className:"button button-primary",type:"submit",disabled:busy || alreadyScheduled || (unscored && !confirmed)}, busy?"Saving interview…":alreadyScheduled?"Initial interview already scheduled":"Review interview")),
    review && h("section",{className:"session-confirmation booking-review","aria-label":"Review interview before booking"},
      h("h3",null,"Review interview before booking"),h("p",null,`Job ${review.jobReference} · criteria revision ${review.request.criteria_revision}`),
      h("p",null,`Application ${review.request.upload_id} · batch ${review.request.batch_id}`),
      h("p",null,scheduleSummary(review.request.scheduled_at,review.request.timezone,review.request.duration_minutes)),
      h("p",null,"No invitation or email will be sent by this booking."),
      h("label",null,h("input",{type:"checkbox",checked:finalConfirmed,disabled:busy,onChange:(e:{target:{checked:boolean}})=>onFinalConfirmed(e.target.checked)})," I confirm this candidate, job and interview start/end time."),
      h("button",{type:"button",className:"button button-secondary",disabled:busy,onClick:onEdit},"Edit booking"),
      h("button",{type:"submit",className:"button button-primary",disabled:busy||alreadyScheduled||!finalConfirmed},busy?"Saving interview…":"Confirm booking")));
}

export function SavedInterviews({rows,criteriaRevision,onOpenInterview}: {rows:Interview[];criteriaRevision:number;onOpenInterview?:(value:Interview)=>void}) {
  return h("div",null,h("h3",null,"Saved interviews"),h("ul",{className:"saved-interviews"},...rows.map(row=>h("li",{key:row.id},
    `Scheduled · ${new Intl.DateTimeFormat("en",{dateStyle:"medium",timeStyle:"short",timeZone:row.timezone}).format(new Date(row.scheduled_at))} (${row.timezone}) · ${row.duration_minutes} minutes`,
    h("p",null,`Job ${row.job_reference} · ${scheduleSummary(row.scheduled_at,row.timezone,row.duration_minutes)}`),
    h("p",{className:"helper-text"},`Candidate ${row.upload_id.slice(0,8)} · criteria revision ${row.criteria_revision}${row.criteria_revision!==criteriaRevision?" (historical)":""}${row.unscored_confirmed?" · Unscored selection confirmed":""}`),
    h("details",{className:"supporting-details"},h("summary",null,"Booking details"),h("p",null,`UTC: ${new Date(row.scheduled_at).toISOString()}`),h("p",null,`Candidate ${row.upload_id} · Candidate invitation managed on interview page`)),
    h(ConsolidatedAssessment,{jobId:row.job_id,batchId:row.batch_id,uploadId:row.upload_id}),
    onOpenInterview && h("button",{type:"button",className:"button button-secondary",onClick:()=>onOpenInterview(row)},row.criteria_revision===criteriaRevision?"Open interview":"Review transcript / privacy")))),
    !rows.length && h("p",null,"No saved interviews loaded."));
}

export function InterviewScheduling({jobId,criteriaRevision,scoring,candidate,onOpenInterview}: {
  jobId:string;criteriaRevision:number;scoring:ScoringBatch|null;candidate:CandidateScore|null;
  onOpenInterview?:(value:Interview)=>void;
}) {
  const [start,setStart]=useState(""); const [zone,setZone]=useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [duration,setDuration]=useState(30);const [confirmed,setConfirmed]=useState(false);
  const [rows,setRows]=useState<Interview[]>([]);const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const [loadingRows,setLoadingRows]=useState(true);
  const [review,setReview]=useState<BookingReview|null>(null);const [finalConfirmed,setFinalConfirmed]=useState(false);
  const [reloadRequired,setReloadRequired]=useState(false);const [loadReady,setLoadReady]=useState(false);
  function clearReview(){setReview(null);setFinalConfirmed(false);}
  const pending=useRef(false);const generation=useRef(0);
  useLayoutEffect(()=>{generation.current++;setStart("");setConfirmed(false);clearReview();setLoadReady(false);setError("");setBusy(false);},[jobId,criteriaRevision,scoring?.batch_id,candidate?.upload_id]);
  useEffect(()=>{const current=generation.current;setRows([]);setLoadingRows(true);
    listInterviews(jobId).then(value=>{if(current===generation.current){setRows(value);setLoadReady(true);setReloadRequired(false);}})
      .catch(()=>{if(current===generation.current)setError("Saved interviews could not be loaded. Reload before scheduling.");})
      .finally(()=>{if(current===generation.current)setLoadingRows(false);});
    return ()=>{generation.current++;};
  },[jobId,criteriaRevision,scoring?.batch_id,candidate?.upload_id]);
  const alreadyScheduled=!!candidate && !!scoring && rows.some(row=>row.batch_id===scoring.batch_id && row.upload_id===candidate.upload_id);
  async function reload() {const current=generation.current;setError("");setLoadReady(false);clearReview();setLoadingRows(true);
    try {const value=await listInterviews(jobId);if(current===generation.current){setRows(value);setLoadReady(true);setReloadRequired(false);}}
    catch {if(current===generation.current)setError("Saved interviews could not be loaded.");}
    finally {if(current===generation.current)setLoadingRows(false);}}
  async function submit(event:FormEvent) {
    event.preventDefault(); if(!candidate || !scoring || pending.current || alreadyScheduled || loadingRows || !loadReady || reloadRequired)return;
    let next:BookingReview;
    try {next=bookingReview(jobId,criteriaRevision,scoring,candidate,start,zone,duration,confirmed);}
    catch {clearReview();setError("Review current eligible results, a future unambiguous time, duration and unscored acknowledgement.");return;}
    if(!review){setReview(next);setFinalConfirmed(false);setError("");return;}
    if(JSON.stringify(next)!==JSON.stringify(review)){clearReview();setError("Selection changed. Review the booking again.");return;}
    if(!finalConfirmed)return;
    // A pre-save list response must not erase the newly saved schedule.
    const current=++generation.current;pending.current=true;setBusy(true);setError("");
    try {const saved=await createInterview(jobId,review.request);
      if(current===generation.current){setRows(old=>[...old.filter(row=>row.id!==saved.id),saved]);clearReview();}
    } catch(failure) {if(current===generation.current){setReloadRequired(true);clearReview();setError(failure instanceof Error?failure.message:"Scheduling was not confirmed. Reload saved interviews.");}}
    finally {pending.current=false;if(current===generation.current)setBusy(false);}
  }
  return h("section", {className:"card", "aria-label":"Interview scheduling"},h("h2",null,"Interview scheduling"),
    candidate && scoring ? h(ScheduleForm,{candidate,start,zone,duration,confirmed,busy:busy||loadingRows||!loadReady||reloadRequired,alreadyScheduled,review,finalConfirmed,onFinalConfirmed:setFinalConfirmed,onEdit:clearReview,onStart:(v:string)=>{clearReview();setStart(v);},onZone:(v:string)=>{clearReview();setZone(v);},onDuration:(v:number)=>{clearReview();setDuration(v);},onConfirmed:(v:boolean)=>{clearReview();setConfirmed(v);},onSubmit:submit})
      : h("p",null,"Select an eligible candidate above to schedule an interview."),
    reloadRequired && h("p",{role:"status"},"Booking outcome needs reconciliation. Reload saved interviews before any further booking attempt."),
    error && h("p",{role:"alert",className:"error-banner"},error),
    h("button",{type:"button",className:"button button-secondary",onClick:()=>void reload(),disabled:busy||loadingRows},"Reload saved interviews"),
    loadingRows ? h("div",null,h("h3",null,"Saved interviews"),h("p",{role:"status"},"Loading saved interviews…")) : h(SavedInterviews,{rows,criteriaRevision,onOpenInterview}));
}
