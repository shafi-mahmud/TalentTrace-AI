import assert from "node:assert/strict";
import {test} from "node:test";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {interviewAccess,supportedLiveKitURL} from "../src/api/livekitInterview.ts";
import {SavedInterviews} from "../src/components/InterviewScheduling.ts";
import type {Interview} from "../src/api/interviews.ts";
const id="12345678-1234-4234-8234-123456789abc";
test('local LiveKit requires development build and loopback page',()=>{
  assert.equal(supportedLiveKitURL('ws://127.0.0.1:7880',true,'127.0.0.1'),true);
  assert.equal(supportedLiveKitURL('ws://127.0.0.1:7880',false,'127.0.0.1'),false);
  assert.equal(supportedLiveKitURL('ws://127.0.0.1:7880',true,'example.test'),false);
  for(const url of ['ws://localhost:7880','ws://192.168.1.2:7880','ws://127.0.0.1:7881','ws://127.0.0.1:7880/?token=x'])
    assert.equal(supportedLiveKitURL(url,true,'127.0.0.1'),false);
});
const interview:Interview={id,job_id:id,job_reference:"TT-JOB-1234567812344234",batch_id:id,upload_id:id,criteria_revision:2,
  scoring_version:"f2-coverage-v1",scheduled_at:"2026-11-20T09:00:00Z",timezone:"UTC",duration_minutes:30,unscored_confirmed:false,status:"scheduled"};
test("only current saved interview exposes recruiter synthetic proof action",()=>{
  let opened=false;
  const html=renderToStaticMarkup(createElement(SavedInterviews,{rows:[interview],criteriaRevision:2,onOpenInterview:()=>{opened=true;}}));
  assert.ok(html.includes("Open interview"));assert.equal(opened,false);
  assert.ok(!renderToStaticMarkup(createElement(SavedInterviews,{rows:[interview],criteriaRevision:3,onOpenInterview:()=>{}})).includes("Open interview"));
});
test("token request scopes owned interview and recruiter without storing or logging token",async t=>{
  t.mock.method(globalThis,"fetch",async (url,options)=>{
    assert.equal(url,`/api/v1/jobs/${id}/interviews/${id}/livekit-token`);
    assert.equal(options?.cache,"no-store");assert.equal(options?.credentials,"include");
    assert.deepEqual(JSON.parse(String(options?.body)),{synthetic_test_confirmed:true});
    return Response.json({server_url:"wss://synthetic.livekit.cloud",token:"synthetic-token-"+"x".repeat(40),expires_in:300});
  });
  assert.equal((await interviewAccess(id,id)).expires_in,300);
});
test("failure details stay sanitized and requests are not automatically retried",async t=>{
  let calls=0;t.mock.method(globalThis,"fetch",async()=>{calls++;throw new Error("private bearer token");});
  await assert.rejects(interviewAccess(id,id),/^Error: Interview access was not confirmed\. Join again only when ready\.$/);
  assert.equal(calls,1);
  for(const status of [404,409,502,503]){
    t.mock.method(globalThis,"fetch",async()=>Response.json({detail:"private credentials"},{status}));
    await assert.rejects(interviewAccess(id,id),error=>!String(error).includes("private credentials"));
  }
  t.mock.method(globalThis,"fetch",async()=>Response.json({server_url:"wss://secret@synthetic.livekit.cloud",token:"x".repeat(40),expires_in:300}));
  await assert.rejects(interviewAccess(id,id),/could not be validated/);
});
