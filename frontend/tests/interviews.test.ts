import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createInterview, isInterview, listInterviews, validTimezone } from "../src/api/interviews.ts";
import type { Interview, InterviewRequest } from "../src/api/interviews.ts";
import { InterviewScheduling, SavedInterviews, ScheduleForm } from "../src/components/InterviewScheduling.ts";
import type { CandidateScore } from "../src/types/screening.ts";

const id="12345678-1234-4234-8234-123456789abc";
const time=new Date(Date.now()+86400000).toISOString();
const request:InterviewRequest={batch_id:id,upload_id:id,criteria_revision:2,scoring_version:"f2-coverage-v1",selection_confirmed:true,
  confirm_eligible_unscored:false,scheduled_at:time,timezone:"Asia/Dhaka",duration_minutes:30};
const response:Interview={id,job_id:id,job_reference:"TT-JOB-1234567812344234",batch_id:id,upload_id:id,criteria_revision:2,
  scoring_version:"f2-coverage-v1",scheduled_at:time,timezone:"Asia/Dhaka",duration_minutes:30,unscored_confirmed:false,status:"scheduled"};
const candidate:CandidateScore={job_reference:response.job_reference,upload_id:id,screening_decision:"eligible",status:"not_evaluated",
  reason:"uncertain_evidence",weights:{skill:50,experience:30,education:20},score:null,dimensions:[]};

test("saved-interview controls remain available without in-memory screening after reload",()=>{
  const html=renderToStaticMarkup(createElement(InterviewScheduling,{jobId:id,criteriaRevision:2,scoring:null,candidate:null}));
  for(const text of ["Interview scheduling","Reload saved interviews","Saved interviews"]) assert.ok(html.includes(text));
  assert.ok(!html.includes('type="submit"'));
});

test("persisted schedule displays the correct timezone and historical revision independently of screening",()=>{
  const html=renderToStaticMarkup(createElement(SavedInterviews,{rows:[{...response,scheduled_at:"2026-11-20T09:00:00Z",unscored_confirmed:true}],criteriaRevision:3}));
  for(const text of ["3:00 PM","Asia/Dhaka","UTC: 2026-11-20T09:00:00.000Z","(historical)","Unscored selection confirmed","Candidate invitation managed on interview page"]) assert.ok(html.includes(text),text);
});

test("scheduling validates UTC, duration, timezone and bounded server result",()=>{
  assert.ok(isInterview(response));
  for(const patch of [{timezone:"../private"},{timezone:"Not/AZone"},{duration_minutes:14},{duration_minutes:180.5},
    {criteria_revision:0},{scheduled_at:"2026-10-20T10:00"},{status:"published"},{meeting_url:"https://fake.test"}])
    assert.ok(!isInterview({...response,...patch}));
  assert.ok(validTimezone("Asia/Dhaka"));assert.ok(!validTimezone("private\0path"));
});

test("create sends references and explicit confirmation; validates response association",async t=>{
  let calls=0;
  t.mock.method(globalThis,"fetch",async (url,options)=>{calls++;assert.equal(url,`/api/v1/jobs/${id}/interviews`);
    assert.equal(new Headers(options?.headers).get("X-TalentTrace-Request"),"1");
    assert.deepEqual(JSON.parse(String(options?.body)),request);return Response.json(response);});
  assert.equal((await createInterview(id,request)).status,"scheduled");assert.equal(calls,1);
  t.mock.method(globalThis,"fetch",async()=>Response.json({...response,criteria_revision:3}));
  await assert.rejects(createInterview(id,request),/could not be validated/);
});

test("network and provider-free API errors are sanitized and never automatically retried",async t=>{
  let calls=0;t.mock.method(globalThis,"fetch",async()=>{calls++;throw new Error("private token content");});
  await assert.rejects(createInterview(id,request),/^Error: Scheduling was not confirmed\. Reload saved interviews before another attempt\.$/);
  assert.equal(calls,1);
  t.mock.method(globalThis,"fetch",async()=>Response.json({detail:"private server content"},{status:409}));
  await assert.rejects(createInterview(id,request),/Scheduling needs review/);
  t.mock.method(globalThis,"fetch",async()=>new Response("private malformed output"));
  await assert.rejects(createInterview(id,request),/could not be validated/);
});

test("listing rejects foreign jobs, duplicate entries and invalid payloads",async t=>{
  t.mock.method(globalThis,"fetch",async()=>Response.json([response]));assert.equal((await listInterviews(id)).length,1);
  for(const rows of [[{...response,job_id:"ffffffff-ffff-4fff-8fff-ffffffffffff"}],[response,response],{detail:"private"}]) {
    t.mock.method(globalThis,"fetch",async()=>Response.json(rows));await assert.rejects(listInterviews(id),/could not be validated/);
  }
});

test("eligible-but-unscored form warns and requires explicit acknowledgement",()=>{
  let confirmed=false;const props={candidate,start:"",zone:"Asia/Dhaka",duration:30,confirmed,busy:false,alreadyScheduled:false,
    onStart:()=>{},onZone:()=>{},onDuration:()=>{},onConfirmed:(v:boolean)=>{confirmed=v;},onSubmit:()=>{}};
  const html=renderToStaticMarkup(createElement(ScheduleForm,props));
  assert.match(html,/Eligible but not scored/);assert.match(html,/Local interview date and time/);
  assert.match(html,/Interview timezone \(IANA\)/);assert.match(html,/disabled=""[^>]*>Schedule interview/);
  const form=ScheduleForm(props);const fields=(form.props.children as React.ReactElement[])[3];
  const children=fields.props.children as React.ReactElement[];
  const acknowledgement=children.at(-2)!;
  acknowledgement.props.children[0].props.onChange({target:{checked:true}});assert.equal(confirmed,true);
  const accepted=renderToStaticMarkup(createElement(ScheduleForm,{...props,confirmed}));
  assert.ok(!/disabled=""[^>]*>Schedule interview/.test(accepted));
  const duplicate=renderToStaticMarkup(createElement(ScheduleForm,{...props,confirmed,alreadyScheduled:true}));
  assert.match(duplicate,/Initial interview already scheduled/);
});
