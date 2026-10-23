import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";
import ts from "typescript";
import {loadApplications,markApplicationsViewed,validateApplications} from "../src/api/applications.ts";

const job="00000000-0000-4000-8000-000000000001";
const row={batch_id:"00000000-0000-4000-8000-000000000002",upload_id:"00000000-0000-4000-8000-000000000003",origin:"trusted_import" as const,available:true,is_new:true};
function summary(){return {job_id:job,received_count:1,new_count:1,unavailable_count:0,invalid_batch_count:0,applications:[row]};}

test("counts cannot mix jobs, duplicate files or falsified totals",()=>{
  assert.equal(validateApplications(summary(),job).new_count,1);
  for(const patch of [{job_id:"another"},{received_count:2},{new_count:0},{unavailable_count:1},{applications:[row,row]},{applications:[{...row,origin:"unknown"}]}])
    assert.throws(()=>validateApplications({...summary(),...patch},job));
});
test("refresh is authenticated GET; viewed writes only displayed identities",async t=>{
  const calls:any[]=[];
  t.mock.method(globalThis,"fetch",async (url:any,init:any)=>{calls.push([url,init]);return init.method==="POST"?new Response(null,{status:204}):Response.json(summary());});
  await loadApplications(job);await markApplicationsViewed(job,[row]);
  assert.equal(calls[0][1].method,undefined);
  assert.equal(calls[0][1].credentials,"include");
  assert.equal(calls[1][1].headers.get("X-TalentTrace-Request"),"1");
  assert.deepEqual(JSON.parse(calls[1][1].body),{applications:[{batch_id:row.batch_id,upload_id:row.upload_id}]});
  assert.match(calls[1][0],/applications\/viewed$/);
});
test("API errors are sanitized and never automatically repeated",async t=>{
  let calls=0;t.mock.method(globalThis,"fetch",async()=>{calls++;return Response.json({email:"PRIVATE_VALUE"},{status:500});});
  await assert.rejects(loadApplications(job),e=>!String(e).includes("PRIVATE_VALUE"));assert.equal(calls,1);
  await assert.rejects(markApplicationsViewed(job,[row]),e=>!String(e).includes("PRIVATE_VALUE"));assert.equal(calls,2);
});
test('malformed responses and transport errors never expose response text or network details',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response('PRIVATE invalid JSON'));
  await assert.rejects(loadApplications(job),/^Error: Applications unavailable\. Try Refresh\.$/);
  t.mock.method(globalThis,'fetch',async()=>{throw Error('PRIVATE transport details');});
  await assert.rejects(loadApplications(job),/^Error: Applications unavailable\. Try Refresh\.$/);
  await assert.rejects(markApplicationsViewed(job,[row]),/^Error: Viewed status was not confirmed\. Refresh before trying again\.$/);
});
