import assert from "node:assert/strict";
import {test} from "node:test";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import CandidateInterview from "../src/components/CandidateInterview.ts";
import {candidateAccess,candidateStatus,exchangeInvitation,invitation,revokeInvitation,takeInvitation} from "../src/api/livekitInterview.ts";
const raw="s".repeat(43);
test("candidate invitation page requires acceptance without rendering token or recruiter login",()=>{
  const html=renderToStaticMarkup(createElement(CandidateInterview,{initialToken:raw}));
  assert.ok(html.includes("Accept invitation"));assert.ok(html.includes("No recruiter login is needed"));
  assert.ok(!html.includes(raw));assert.ok(!html.includes("Sign in"));assert.ok(!html.includes("password"));
});
test("invitation fragment is removed from browser history without storage",()=>{
  let removed="";
  const value=takeInvitation({hash:`#invite=${raw}`,pathname:"/interview-join"} as Location,
    {replaceState:(_a:unknown,_b:string,url:string)=>{removed=url;}} as unknown as History);
  assert.equal(value,raw);assert.equal(removed,"/interview-join");
  assert.equal(takeInvitation({hash:"#invite=unsafe",pathname:"/interview-join"} as Location,
    {replaceState:()=>{}} as unknown as History),null);
});
test("candidate exchanges a body-only bearer once and joins with HttpOnly session",async t=>{
  let calls=0;
  t.mock.method(globalThis,"fetch",async(url,options)=>{
    calls++;assert.equal(options?.credentials,"include");assert.equal(options?.cache,"no-store");
    assert.ok(!String(url).includes(raw));
    if(String(url).endsWith("exchange")){
      assert.deepEqual(JSON.parse(String(options?.body)),{token:raw});return Response.json({status:"ready"});
    }
    assert.deepEqual(JSON.parse(String(options?.body)),{synthetic_test_confirmed:true});
    return Response.json({server_url:"wss://synthetic.livekit.cloud",token:"x".repeat(40),expires_in:30});
  });
  await exchangeInvitation(raw);assert.equal((await candidateAccess()).expires_in,30);assert.equal(calls,2);
});
test("expiry revocation and duplicate claims are sanitized without retry",async t=>{
  for(const status of [401,409,429,502]){
    let calls=0;t.mock.method(globalThis,"fetch",async()=>{calls++;return Response.json({detail:"private token"},{status});});
    await assert.rejects(exchangeInvitation(raw),error=>!String(error).includes("private token"));assert.equal(calls,1);
    await assert.rejects(candidateStatus(),/unavailable/);
  }
});
test("owner invitation generation and revocation use owned routes only",async t=>{
  t.mock.method(globalThis,"fetch",async(url,options)=>{
    assert.ok(String(url).startsWith("/api/v1/jobs/job/interviews/interview/invitation"));
    assert.equal(options?.credentials,"include");assert.equal(options?.method,"POST");
    return Response.json({token:raw,expires_at:"2026-10-20T10:00:00Z"});
  });
  assert.equal((await invitation("job","interview")).token,raw);await revokeInvitation("job","interview");
});
