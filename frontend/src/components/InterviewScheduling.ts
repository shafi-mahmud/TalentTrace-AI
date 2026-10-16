import ConsolidatedAssessment from './ConsolidatedAssessment.ts';
import { createElement as h, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createInterview, listInterviews } from "../api/interviews.ts";
import { localSchedule, timezoneOptions } from "./interviewTime.ts";
import type { Interview } from "../api/interviews.ts";
import type { CandidateScore, ScoringBatch } from "../types/screening";

export function ScheduleForm({candidate, start, zone, duration, confirmed, busy, alreadyScheduled, onStart, onZone, onDuration, onConfirmed, onSubmit}: {
  candidate: CandidateScore; start: string; zone: string; duration: number; confirmed: boolean; busy: boolean; alreadyScheduled: boolean;
  onStart: (v: string) => void; onZone: (v: string) => void; onDuration: (v: number) => void; onConfirmed: (v: boolean) => void; onSubmit: (e: FormEvent) => void;
}) {
  const unscored = candidate.status !== "scored";
  const preview = start ? localSchedule(start, zone) : null;
  return h("form", {onSubmit}, h("p", null, `Candidate reference: ${candidate.upload_id}`),
    h("p", {className:"helper-text"}, "You select this candidate. Scheduling does not change screening or hiring decisions. No meeting link or notification is created."),
    unscored && h("p", {role:"status", className:"error-banner"}, "Eligible but not scored. Review the missing or uncertain weighted evidence before selection."),
    h("fieldset", {disabled:busy || alreadyScheduled},
      h("legend", null, "Initial interview"),
      h("label", {htmlFor:"interview-start"}, "Local interview date and time"),
      h("input", {id:"interview-start",type:"datetime-local",value:start,required:true,onChange:(e:{target:{value:string}})=>onStart(e.target.value)}),
      h("label", {htmlFor:"interview-zone"}, "Interview timezone (IANA)"),
      h("select", {id:"interview-zone",value:zone,required:true,onChange:(e:{target:{value:string}})=>onZone(e.target.value)},
        ...timezoneOptions(zone).map(value=>h("option",{key:value,value},value))),
      h("p", {className:"helper-text"}, "Enter the time in the selected timezone. Check UTC below before saving."),
      preview && h("p", {role:"status",className:"helper-text"}, preview.error ?? `Local: ${start.replace("T", " ")} (${zone}) · UTC: ${preview.utc}`),
      h("label", {htmlFor:"interview-duration"}, "Duration (minutes)"),
      h("input", {id:"interview-duration",type:"number",value:Number.isFinite(duration)?duration:"",min:15,max:180,step:1,required:true,onChange:(e:{target:{value:string}})=>onDuration(e.target.value === ""?NaN:Number(e.target.value))}),
      unscored && h("label", null, h("input", {type:"checkbox",checked:confirmed,onChange:(e:{target:{checked:boolean}})=>onConfirmed(e.target.checked)}), " I reviewed the uncertainty and explicitly select this eligible, unscored candidate."),
      h("button", {className:"button button-primary",type:"submit",disabled:busy || alreadyScheduled || (unscored && !confirmed)}, busy?"Saving interview…":alreadyScheduled?"Initial interview already scheduled":"Schedule interview")));
}

export function SavedInterviews({rows,criteriaRevision,onOpenInterview}: {rows:Interview[];criteriaRevision:number;onOpenInterview?:(value:Interview)=>void}) {
  return h("div",null,h("h3",null,"Saved interviews"),h("ul",{className:"saved-interviews"},...rows.map(row=>h("li",{key:row.id},
    `Scheduled · ${new Intl.DateTimeFormat("en",{dateStyle:"medium",timeStyle:"short",timeZone:row.timezone}).format(new Date(row.scheduled_at))} (${row.timezone}) · ${row.duration_minutes} minutes`,
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
  const pending=useRef(false);const generation=useRef(0);
  useLayoutEffect(()=>{generation.current++;setStart("");setConfirmed(false);setError("");setBusy(false);},[jobId,criteriaRevision,scoring?.batch_id,candidate?.upload_id]);
  useEffect(()=>{const current=generation.current;setRows([]);setLoadingRows(true);
    listInterviews(jobId).then(value=>{if(current===generation.current)setRows(value);})
      .catch(()=>{if(current===generation.current)setError("Saved interviews could not be loaded. Reload before scheduling.");})
      .finally(()=>{if(current===generation.current)setLoadingRows(false);});
    return ()=>{generation.current++;};
  },[jobId,criteriaRevision,scoring?.batch_id,candidate?.upload_id]);
  const alreadyScheduled=!!candidate && !!scoring && rows.some(row=>row.batch_id===scoring.batch_id && row.upload_id===candidate.upload_id);
  async function reload() {const current=generation.current;setError("");setLoadingRows(true);
    try {const value=await listInterviews(jobId);if(current===generation.current)setRows(value);}
    catch {if(current===generation.current)setError("Saved interviews could not be loaded.");}
    finally {if(current===generation.current)setLoadingRows(false);}}
  async function submit(event:FormEvent) {
    event.preventDefault(); if(!candidate || !scoring || pending.current || alreadyScheduled)return;
    const schedule=localSchedule(start,zone);
    if(!schedule.utc) {setError(schedule.error ?? "Enter a valid local date and time.");return;}
    const time=schedule.utc;
    if(!Number.isInteger(duration) || duration<15 || duration>180) {setError("Use a duration of 15 to 180 whole minutes.");return;}
    if(scoring.job_id!==jobId || scoring.criteria_revision!==criteriaRevision || candidate.screening_decision!=="eligible" || (candidate.status!=="scored" && !confirmed)) {setError("Current eligible screening results and explicit selection are required.");return;}
    // A pre-save list response must not erase the newly saved schedule.
    const current=++generation.current;pending.current=true;setBusy(true);setError("");
    try {const saved=await createInterview(jobId,{batch_id:scoring.batch_id,upload_id:candidate.upload_id,
      criteria_revision:scoring.criteria_revision,scoring_version:scoring.scoring_version,selection_confirmed:true,
      confirm_eligible_unscored:candidate.status!=="scored" && confirmed,scheduled_at:time,timezone:zone,duration_minutes:duration});
      if(current===generation.current)setRows(old=>[...old.filter(row=>row.id!==saved.id),saved]);
    } catch(failure) {if(current===generation.current)setError(failure instanceof Error?failure.message:"Scheduling was not confirmed. Reload saved interviews.");}
    finally {pending.current=false;if(current===generation.current)setBusy(false);}
  }
  return h("section", {className:"card", "aria-label":"Interview scheduling"},h("h2",null,"Interview scheduling"),
    candidate && scoring ? h(ScheduleForm,{candidate,start,zone,duration,confirmed,busy:busy||loadingRows,alreadyScheduled,onStart:setStart,onZone:setZone,onDuration:setDuration,onConfirmed:setConfirmed,onSubmit:submit})
      : h("p",null,"Select an eligible candidate above to schedule an interview."),
    error && h("p",{role:"alert",className:"error-banner"},error),
    h("button",{type:"button",className:"button button-secondary",onClick:()=>void reload(),disabled:busy||loadingRows},"Reload saved interviews"),
    loadingRows ? h("div",null,h("h3",null,"Saved interviews"),h("p",{role:"status"},"Loading saved interviews…")) : h(SavedInterviews,{rows,criteriaRevision,onOpenInterview}));
}
