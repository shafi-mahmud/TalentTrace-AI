import { createElement as h, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createInterview, listInterviews, utcSchedule, validTimezone } from "../api/interviews.ts";
import type { Interview } from "../api/interviews.ts";
import type { CandidateScore, ScoringBatch } from "../types/screening";

export function ScheduleForm({candidate, start, zone, duration, confirmed, busy, alreadyScheduled, onStart, onZone, onDuration, onConfirmed, onSubmit}: {
  candidate: CandidateScore; start: string; zone: string; duration: number; confirmed: boolean; busy: boolean; alreadyScheduled: boolean;
  onStart: (v: string) => void; onZone: (v: string) => void; onDuration: (v: number) => void; onConfirmed: (v: boolean) => void; onSubmit: (e: FormEvent) => void;
}) {
  const unscored = candidate.status !== "scored";
  return h("form", {onSubmit}, h("p", null, `Candidate reference: ${candidate.upload_id}`),
    h("p", {className:"helper-text"}, "You select this candidate. Scheduling does not change screening or hiring decisions. No meeting link or notification is created."),
    unscored && h("p", {role:"status", className:"error-banner"}, "Eligible but not scored. Review the missing or uncertain weighted evidence before selection."),
    h("fieldset", {disabled:busy || alreadyScheduled},
      h("legend", null, "Initial interview"),
      h("label", {htmlFor:"interview-start"}, "Start time (UTC)"),
      h("input", {id:"interview-start",type:"datetime-local",value:start,required:true,onChange:(e:{target:{value:string}})=>onStart(e.target.value)}),
      h("label", {htmlFor:"interview-zone"}, "Display timezone (IANA)"),
      h("input", {id:"interview-zone",value:zone,maxLength:64,required:true,onChange:(e:{target:{value:string}})=>onZone(e.target.value)}),
      h("p", {className:"helper-text"}, "Enter UTC above; the timezone controls display, not interpretation of that input."),
      h("label", {htmlFor:"interview-duration"}, "Duration (minutes)"),
      h("input", {id:"interview-duration",type:"number",value:Number.isFinite(duration)?duration:"",min:15,max:180,step:1,required:true,onChange:(e:{target:{value:string}})=>onDuration(e.target.value === ""?NaN:Number(e.target.value))}),
      unscored && h("label", null, h("input", {type:"checkbox",checked:confirmed,onChange:(e:{target:{checked:boolean}})=>onConfirmed(e.target.checked)}), " I reviewed the uncertainty and explicitly select this eligible, unscored candidate."),
      h("button", {className:"button button-primary",type:"submit",disabled:busy || alreadyScheduled || (unscored && !confirmed)}, busy?"Saving interview…":alreadyScheduled?"Initial interview already scheduled":"Schedule interview")));
}

export function InterviewScheduling({scoring, candidate}: {scoring:ScoringBatch; candidate:CandidateScore|null}) {
  const [start,setStart]=useState(""); const [zone,setZone]=useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [duration,setDuration]=useState(30);const [confirmed,setConfirmed]=useState(false);
  const [rows,setRows]=useState<Interview[]>([]);const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const pending=useRef(false);const generation=useRef(0);
  useLayoutEffect(()=>{generation.current++;setStart("");setConfirmed(false);setError("");setBusy(false);},[scoring.job_id,scoring.batch_id,scoring.criteria_revision,candidate?.upload_id]);
  useEffect(()=>{const current=generation.current;setRows([]);
    listInterviews(scoring.job_id).then(value=>{if(current===generation.current)setRows(value);})
      .catch(()=>{if(current===generation.current)setError("Saved interviews could not be loaded. Reload before scheduling.");});
    return ()=>{generation.current++;};
  },[scoring.job_id,scoring.batch_id,scoring.criteria_revision,candidate?.upload_id]);
  const alreadyScheduled=!!candidate && rows.some(row=>row.batch_id===scoring.batch_id && row.upload_id===candidate.upload_id);
  async function reload() {const current=generation.current;setError("");
    try {const value=await listInterviews(scoring.job_id);if(current===generation.current)setRows(value);}
    catch {if(current===generation.current)setError("Saved interviews could not be loaded.");}}
  async function submit(event:FormEvent) {
    event.preventDefault(); if(!candidate || pending.current || alreadyScheduled)return;
    const time=utcSchedule(start);
    if(!time || !validTimezone(zone) || !Number.isInteger(duration) || duration<15 || duration>180) {setError("Use a future UTC time, valid IANA timezone and 15–180 whole minutes.");return;}
    if(candidate.screening_decision!=="eligible" || (candidate.status!=="scored" && !confirmed)) {setError("Explicit eligible candidate selection is required.");return;}
    // A pre-save list response must not erase the newly saved schedule.
    const current=++generation.current;pending.current=true;setBusy(true);setError("");
    try {const saved=await createInterview(scoring.job_id,{batch_id:scoring.batch_id,upload_id:candidate.upload_id,
      criteria_revision:scoring.criteria_revision,scoring_version:scoring.scoring_version,selection_confirmed:true,
      confirm_eligible_unscored:candidate.status!=="scored" && confirmed,scheduled_at:time,timezone:zone,duration_minutes:duration});
      if(current===generation.current)setRows(old=>[...old.filter(row=>row.id!==saved.id),saved]);
    } catch(failure) {if(current===generation.current)setError(failure instanceof Error?failure.message:"Scheduling was not confirmed. Reload saved interviews.");}
    finally {pending.current=false;if(current===generation.current)setBusy(false);}
  }
  return h("section", {className:"card", "aria-label":"Interview scheduling"},h("h2",null,"Interview scheduling"),
    candidate ? h(ScheduleForm,{candidate,start,zone,duration,confirmed,busy,alreadyScheduled,onStart:setStart,onZone:setZone,onDuration:setDuration,onConfirmed:setConfirmed,onSubmit:submit})
      : h("p",null,"Select an eligible candidate above to schedule an interview."),
    error && h("p",{role:"alert",className:"error-banner"},error),
    h("button",{type:"button",className:"button button-secondary",onClick:()=>void reload(),disabled:busy},"Reload saved interviews"),
    h("h3",null,"Saved interviews"),h("ul",null,...rows.map(row=>h("li",{key:row.id},
      `Scheduled · ${new Intl.DateTimeFormat("en",{dateStyle:"medium",timeStyle:"short",timeZone:row.timezone}).format(new Date(row.scheduled_at))} (${row.timezone}) · ${row.duration_minutes} minutes`,
      h("p",{className:"helper-text"},`Candidate ${row.upload_id} · criteria revision ${row.criteria_revision}${row.criteria_revision!==scoring.criteria_revision?" (historical)":""}${row.unscored_confirmed?" · Unscored selection confirmed":""} · Meeting link not configured`)))),
    !rows.length && h("p",null,"No saved interviews loaded."));
}
