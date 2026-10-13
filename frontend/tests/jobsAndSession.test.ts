import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { authenticatedFetch, account, signIn, signOut } from "../src/api/session.ts";
import { isSavedJob, workingJob, listJobs, createJob, saveCriteria, loadConversation } from "../src/api/jobs.ts";
import type { SavedJob } from "../src/api/jobs.ts";
import { initialRecruiterWorkspaceState, recruiterWorkspaceReducer, restoreActiveJob, rememberActiveJob, criteriaSaveStatus } from "../src/state/recruiterWorkspace.ts";
import { initialRecruiterChatState, recruiterChatReducer } from "../src/state/recruiterChatState.ts";
import ScreeningCriteriaReview from "../src/components/ScreeningCriteriaReview.ts";

const id = "12345678-1234-4234-8234-123456789abc";
const reference = "TT-JOB-1234567812344234";
const criterion = {criterion_id: "python", description: "Python", category: "skill" as const, is_hard: false};
function job(): SavedJob {
  return {id, job_reference: reference, job_title: "Engineer", revision: 1,
    suggestions: {job_title: "Engineer", criteria: [{...criterion}]},
    sources: [{criterion_id: "python", source: "recruiter_input", evidence: "Python"}],
    snapshot: null, draft: null, conversation_id: null};
}

test("saving scoring weights uses approval revision and cannot send invalid weights", async t => {
  const weights = {skill: 100, experience: 0, education: 0};
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    calls++;
    assert.deepEqual(JSON.parse(String(options?.body)), {revision: 1, criteria: [criterion], confirmed: true, weights});
    return Response.json({...job(), scoring_weights: weights});
  });
  const saved = await saveCriteria(id, 1, [criterion], true, weights);
  assert.deepEqual(workingJob(saved).weights, weights);
  await assert.rejects(saveCriteria(id, 1, [criterion], true, {...weights, skill: 99}), /totaling 100/);
  assert.equal(calls, 1);
  assert.ok(!isSavedJob({...saved, scoring_weights: {...weights, skill: 101}}));
});

test("session transport includes cookies and mutation marker without exposing server errors", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async (_url, init) => {
      assert.equal(init?.credentials, "include");
      assert.equal(new Headers(init?.headers).get("X-TalentTrace-Request"), "1");
      return new Response('{"private":"PRIVATE_SERVER_ERROR"}', {status: 503});
    };
    await assert.rejects(signIn("synthetic@example.test", "synthetic-password"), /Sign-in failed/);
    await assert.rejects(signOut(), /Sign-out was not confirmed/);
    await authenticatedFetch("/test", {method: "POST"});
    globalThis.fetch = async () => new Response("", {status: 401});
    assert.equal(await account(), null);
  } finally {globalThis.fetch = old;}
});

test("saved job validates confirmation association and bounded policy provenance", () => {
  const value = job();
  assert.ok(isSavedJob(value));
  assert.equal(workingJob(value).reviewed, false);
  value.snapshot = {job_reference: reference, job_title: "Engineer", criteria_confirmed: true, criteria: [{...criterion}]};
  assert.ok(isSavedJob(value));
  assert.equal(workingJob(value).reviewed, true);
  const bad = structuredClone(value);
  bad.snapshot!.criteria[0].is_hard = true;
  assert.ok(!isSavedJob(bad));
  assert.ok(!isSavedJob({...value, sources: [...value.sources, ...value.sources]}));
  assert.ok(!isSavedJob({...value, sources: [{...value.sources[0], evidence: "private\0text"}]}));
  assert.ok(!isSavedJob({...value, sources: [{...value.sources[0], criterion_id: "unknown"}]}));
  assert.ok(!isSavedJob({...value, sources: [{...value.sources[0], source: "company_policy", citation_id: "arbitrary-path", source_title: "Demo"}]}));
});

test("saved criteria are shared automatically; editing clears approval without losing the job identity", () => {
  const value = job();
  value.snapshot = {job_reference: reference, job_title: "Engineer", criteria_confirmed: true, criteria: [{...criterion}]};
  let state = recruiterWorkspaceReducer(initialRecruiterWorkspaceState, {type: "draft_generated", draft: workingJob(value)});
  assert.equal(state.activeDraftId, id); // No transfer action required.
  state = recruiterWorkspaceReducer(state, {type: "mode_changed", mode: "cv"});
  assert.equal(state.drafts[id].jobReference, reference);
  state = recruiterWorkspaceReducer(state, {type: "criteria_changed", draftId: id, criteria: [{...criterion, is_hard: true}]});
  assert.equal(state.drafts[id].reviewed, false);
  assert.equal(state.drafts[id].savedSnapshot, null);
  state = recruiterWorkspaceReducer(state, {type: "new_chat"});
  assert.equal(state.activeDraftId, null);
});

test("job API sends only bounded criteria and explicit approval, preserving server reference", async () => {
  const old = globalThis.fetch;
  const value = job();
  try {
    globalThis.fetch = async (_url, init) => {
      if (init?.method === "POST") assert.deepEqual(JSON.parse(String(init.body)), {job_title: "Engineer"});
      if (init?.method === "PUT") assert.deepEqual(JSON.parse(String(init.body)), {revision: 1, criteria: [criterion], confirmed: true});
      return new Response(JSON.stringify(init?.method ? value : [value]));
    };
    assert.equal((await listJobs())[0].id, id);
    assert.equal((await createJob("Engineer")).job_reference, reference);
    assert.equal((await saveCriteria(id, 1, [criterion], true)).id, id);
    globalThis.fetch = async () => new Response("PRIVATE_ERROR", {status: 409});
    await assert.rejects(saveCriteria(id, 1, [criterion], true), /Job changed/);
  } finally {globalThis.fetch = old;}
});

test("restored conversations validate identity and replace unrelated local turns", async () => {
  const old = globalThis.fetch;
  const reply = {status: "clarification", intent: "create_job_description", assistant_message: "What skills?", conversation_id: id, missing_fields: ["required_skills"]};
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({id, turns: [{message: "Engineer role", reply}]}));
    const restored = await loadConversation(id);
    const state = recruiterChatReducer({...initialRecruiterChatState, input: "Unsent old input", messages: [{role: "assistant", text: "Old context"}]},
      {type: "conversation_restored", conversationId: id, messages: [{role: "recruiter", text: restored.turns[0].message}, {role: "assistant", text: restored.turns[0].reply.assistant_message}]});
    assert.equal(state.conversationId, id); assert.equal(state.input, ""); assert.equal(state.messages.length, 2);
    globalThis.fetch = async () => new Response(JSON.stringify({id, turns: [{message: "Engineer", reply: {...reply, conversation_id: "different"}}]}));
    await assert.rejects(loadConversation(id), /could not be validated/);
  } finally {globalThis.fetch = old;}
});

test("policy suggestions are visibly synthetic/preferred and need explicit confirmation", () => {
  const sources = [{criterion_id: "python", source: "company_policy" as const, evidence: "following access controls",
    citation_id: "policy:12345678123456781234567812345678:1111111111111111:2222222222222222:0000", source_title: "Synthetic Demo Company Policy"}];
  const html = renderToStaticMarkup(createElement(ScreeningCriteriaReview, {suggestions: job().suggestions, criteria: [criterion], sources,
    reviewed: false, jobReference: reference, disabled: false, onChange: () => {}, onReviewedChange: () => {}, onConfirm: () => assert.fail("Render cannot approve")}));
  assert.match(html, /Synthetic demo policy/); assert.match(html, /following access controls/);
  assert.match(html, /Awaiting your review/); assert.match(html, /value="preferred" selected/);
  assert.match(html, /Confirm requirements/); assert.doesNotMatch(html, /Set up candidate screening/);
});


test("active-job pointer restores per recruiter without storing private job contents", () => {
  const values = new Map<string, string>();
  const storage = {getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => {values.set(key, value);}, removeItem: (key: string) => {values.delete(key);}};
  rememberActiveJob(storage, "recruiter-a", id);
  assert.equal(restoreActiveJob(storage, "recruiter-a"), id);
  assert.equal(restoreActiveJob(storage, "recruiter-b"), null);
  const context = {...initialRecruiterWorkspaceState, activeDraftId: restoreActiveJob(storage, "recruiter-a")};
  const restored = recruiterWorkspaceReducer(context, {type: "saved_job_reloaded", context, draft: workingJob(job())});
  assert.equal(restored.activeDraftId, id);
  assert.equal(restored.drafts[id].jobReference, reference);
  rememberActiveJob(storage, "recruiter-a", null);
  assert.equal(restoreActiveJob(storage, "recruiter-a"), null);
  assert.equal(restoreActiveJob({getItem: () => {throw Error("blocked");}}, "a"), null);
  values.set("talenttrace-active-job:recruiter-a", "invalid");
  assert.equal(restoreActiveJob(storage, "recruiter-a"), null);
});

test("late saved-job reload cannot overwrite edits, another job or New Chat", () => {
  const context = recruiterWorkspaceReducer(initialRecruiterWorkspaceState, {type: "draft_generated", draft: workingJob(job())});
  const edited = recruiterWorkspaceReducer(context, {type: "criteria_changed", draftId: id, criteria: [{...criterion, is_hard: true}]});
  const action = {type: "saved_job_reloaded" as const, context, draft: workingJob(job())};
  assert.equal(recruiterWorkspaceReducer(edited, action), edited);
  const fresh = recruiterWorkspaceReducer(context, {type: "new_chat"});
  assert.equal(recruiterWorkspaceReducer(fresh, action), fresh);
  const other = {...context, activeDraftId: "another-job"};
  assert.equal(recruiterWorkspaceReducer(other, action), other);
  assert.equal(recruiterWorkspaceReducer(context, {...action, draft: null}).activeDraftId, null);
});


test("save indicator distinguishes unsaved criteria from persisted approval", () => {
  const draft = workingJob(job());
  assert.equal(criteriaSaveStatus(draft), "Job saved - Review needed");
  assert.equal(criteriaSaveStatus({...draft, reviewed: true}), "Job saved - Requirements confirmed");
  assert.equal(criteriaSaveStatus({...draft, criteria: [{...criterion, is_hard: true}]}), "Job saved - Criteria edits not saved");
});


test("new manual job accepts empty criteria only before confirmation without a JD or sources", async () => {
  const manual = {...job(), suggestions: {job_title: "Engineer", criteria: []}, sources: []};
  assert.ok(isSavedJob(manual));
  assert.equal(workingJob(manual).origin, "manual");
  assert.equal(workingJob(manual).reviewed, false);
  assert.ok(!isSavedJob({...manual, conversation_id: id}));
  assert.ok(!isSavedJob({...manual, sources: job().sources}));
  assert.ok(!isSavedJob({...manual, snapshot: {job_reference: reference, job_title: "Engineer", criteria_confirmed: true, criteria: []}}));
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify(manual));
    assert.equal((await createJob("Engineer")).id, id);
    globalThis.fetch = async () => new Response(JSON.stringify([manual]));
    assert.equal((await listJobs())[0].id, id);
  } finally {globalThis.fetch = previous;}
});


test("sign-in uses bounded server cooldown without retrying or exposing error bodies", async()=>{
  const {signIn,SignInRateLimitError}=await import("../src/api/session.ts");
  const original=globalThis.fetch;let calls=0;
  try {
    for(const [header,expected] of [["42",42],["0",300],["9999",300],["bad",300],[null,300]] as const){
      globalThis.fetch=async()=>{calls++;return new Response("PRIVATE_ERROR",{status:429,headers:header===null?{}:{"Retry-After":header}});};
      await assert.rejects(()=>signIn("synthetic@example.test","synthetic-test-only"),error=>{
        assert.ok(error instanceof SignInRateLimitError);assert.equal(error.retryAfterSeconds,expected);assert.ok(!error.message.includes("PRIVATE_ERROR"));return true;
      });
    }
    assert.equal(calls,5);
  } finally {globalThis.fetch=original;}
});
