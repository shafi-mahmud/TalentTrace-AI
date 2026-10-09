import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { isValidRecruiterMessage, RecruiterChatRequestError, sendRecruiterMessage } from "../src/api/recruiterChat.ts";
import { publishDraft } from "../src/api/jobPublishing.ts";
import { ChatMessageView, RecruiterChatPage, replyToChatMessage } from "../src/components/chatPresentation.ts";

function result() {
  return {
    status: "jd_generated", intent: "create_job_description", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910",
    draft_id: "fe90b431-a0bf-44f5-908b-316001e1af15", assistant_message: "Your draft is ready. Human review required.",
    screening_suggestions: {job_title: "Engineer", criteria: [{criterion_id: "skill-python", description: "Python", category: "skill", is_hard: false}]},
    screening_suggestion_sources: [{criterion_id: "skill-python", source: "recruiter_input", evidence: "Required skills are Python."}],
    publishing_context: {location: null, employment_type: null, work_arrangement: null},
    job_description_result: {
      status: "draft", human_review_required: true, provider: "groq", model: "openai/gpt-oss-120b", retrieval_mode: "semantic_bge_pgvector",
      job_description: { title: "Engineer", summary: "Build secure backend services.", responsibilities: ["Write tests"], required_skills: ["Python"], preferred_skills: [], qualifications: ["Backend skills"], policy_citation_ids: ["synthetic"] },
      grounding_citations: [{ citation_id: "synthetic", source_title: "Synthetic Demo Company Policy", heading_paths: [["Skills"]] }],
    },
  };
}

test("chatbot success preserves the validated semantic JD result", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json(result()));
  const reply = await sendRecruiterMessage("Create a JD with Python skills.");
  assert.equal(reply.status, "jd_generated");
  if (reply.status === "jd_generated") assert.equal(reply.job_description_result.human_review_required, true);
});

test("clarification response renders the actual missing-field labels", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ status: "clarification", intent: "create_job_description", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: "Please include responsibilities and skills.", missing_fields: ["responsibilities", "required_skills"] }));
  const reply = await sendRecruiterMessage("Create an engineer JD.");
  assert.equal(reply.status, "clarification");
  if (reply.status !== "clarification") assert.fail("Expected clarification");
  const html = renderToStaticMarkup(createElement(ChatMessageView, { message: { role: "assistant", text: reply.assistant_message, missingFields: reply.missing_fields } }));
  assert.match(html, /Responsibilities/);
  assert.match(html, /Required skills/);
  assert.match(html, /Please include responsibilities/);
});

test("recruiter message rendering escapes HTML", () => {
  const html = renderToStaticMarkup(createElement(ChatMessageView, { message: { role: "recruiter", text: "<script>unsafe</script>" } }));
  assert.ok(!html.includes("<script>"));
  assert.match(html, /&lt;script&gt;/);
});

test("chatbot does not bypass existing draft/review runtime validation", async (t) => {
  const body = result();
  body.job_description_result.human_review_required = false;
  t.mock.method(globalThis, "fetch", async () => Response.json(body));
  await assert.rejects(sendRecruiterMessage("Create a JD."));
});

test("unsupported intent is displayed without claiming publication", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ status: "unsupported", intent: "unsupported", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: "Only JD creation is available." }));
  assert.equal((await sendRecruiterMessage("Publish a job." )).status, "unsupported");
});

test("unsafe server error text is never shown", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ message: "PRIVATE_SECRET" }, { status: 502 }));
  await assert.rejects(sendRecruiterMessage("Create a JD."), (error: Error) => !error.message.includes("PRIVATE_SECRET"));
});

test("network failure is reported as uncertain and is never automatically retried", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => { calls++; throw new TypeError("network failure"); });
  await assert.rejects(sendRecruiterMessage("Create a JD."), (error: Error) => {
    assert.ok(error instanceof RecruiterChatRequestError);
    assert.equal((error as RecruiterChatRequestError).uncertain, true);
    return error.message.includes("may have been received");
  });
  assert.equal(calls, 1);
});


test("multiline job instructions and comparisons pass the submission guard", () => {
  assert.equal(isValidRecruiterMessage("Create a JD.\r\nSkills:\tPython >= 3.11"), true);
  assert.equal(isValidRecruiterMessage("Build transcript/resume processing services"), true);
  for (const text of ["", "x".repeat(4001), "unsafe\x00", "unsafe\x1b", "unsafe\u202e"]) {
    assert.equal(isValidRecruiterMessage(text), false);
  }
});

test("optional evidence clarification uses public field labels", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({status: "clarification", intent: "create_job_description", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: "Clarify work arrangement and experience.", missing_fields: ["work_arrangement", "minimum_experience_years"]}));
  const reply = await sendRecruiterMessage("Create a JD.");
  if (reply.status !== "clarification") assert.fail("Expected clarification");
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message: {role: "assistant", text: reply.assistant_message, missingFields: reply.missing_fields}}));
  assert.match(html, /Work arrangement/);
  assert.match(html, /Minimum experience years/);
});


test("chat-first page contains the conversation without a manual form or result panel", () => {
  const html = renderToStaticMarkup(createElement(RecruiterChatPage, { children: createElement("section", {role: "log"}, "Conversation") }));
  assert.match(html, /Job description assistant/);
  assert.match(html, /role="log"/);
  assert.ok(!html.includes("Manual role requirements"));
  assert.ok(!html.includes("result-card"));
  assert.ok(!html.includes("job-title"));
});

test("generated draft is inside the rich assistant message with review and citations", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json(result()));
  const message = replyToChatMessage(await sendRecruiterMessage("Create a JD."));
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message}));
  assert.match(html, /chat-assistant/);
  assert.match(html, /chat-draft/);
  for (const text of ["Draft", "Human review required", "Engineer", "Summary", "Responsibilities", "Required Skills", "Qualifications", "Policy Grounding", "Synthetic Demo Company Policy", "Technical details", "synthetic"]) assert.ok(html.includes(text));
  assert.match(html, /Draft saved to your job/);
});

test("generated chat card leaves criteria review in the shared Candidate Screening workspace", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json(result()));
  const message = replyToChatMessage(await sendRecruiterMessage("Create a JD."));
  if (!message.draftId || !message.screeningSuggestions || !message.screeningSuggestionSources) assert.fail("Expected criteria suggestions");
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message, criteriaDraft: {
    draftId: message.draftId, suggestions: message.screeningSuggestions, sources: message.screeningSuggestionSources,
    criteria: message.screeningSuggestions.criteria, reviewed: false,
  }, onCriteriaChange: () => {}, onCriteriaReviewed: () => {}, onContinue: () => {}}));
  assert.match(html, /Screening requirements are available in Candidate Screening/);
  assert.ok(!html.includes("Editable screening criteria"));
  assert.ok(!html.includes("Continue to CV screening"));
  assert.ok(!html.includes('type="checkbox"'));

});

test("clarification maps directly into an assistant conversation message", () => {
  const message = replyToChatMessage({status: "clarification", intent: "create_job_description", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: "Please include skills.", missing_fields: ["required_skills"]});
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message}));
  assert.match(html, /chat-assistant/);
  assert.match(html, /Required skills/);
  assert.ok(!html.includes("chat-draft"));
});

test("failed chat attempt is visibly uncertain and only offers same-session retry when safe", () => {
  const unsafeToRetry = renderToStaticMarkup(createElement(ChatMessageView, {message: {role: "recruiter", text: "Create a JD.",
    localMessageId: "turn-1", sendState: "uncertain", sendError: "Connection lost.", retryAvailable: false}}));
  assert.match(unsafeToRetry, /Delivery was not confirmed/);
  assert.match(unsafeToRetry, /may have accepted/);
  assert.ok(!unsafeToRetry.includes("Retry in this conversation"));
  const retryable = renderToStaticMarkup(createElement(ChatMessageView, {message: {role: "recruiter", text: "Follow-up",
    localMessageId: "turn-2", sendState: "uncertain", retryAvailable: true}, onRetry: () => {}}));
  assert.match(retryable, /Retry in this conversation/);
});

test("conversation id is sent back on follow-up and draft-unchanged is a normal chat reply", async (t) => {
  let requestBody: Record<string, unknown> = {};
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    requestBody = JSON.parse(String(options?.body));
    return Response.json({status: "draft_unchanged", intent: "create_job_description", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: "Your current draft is unchanged."});
  });
  const reply = await sendRecruiterMessage("Thanks", "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910");
  assert.equal(requestBody.conversation_id, "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910");
  assert.equal(reply.status, "draft_unchanged");
  assert.equal(replyToChatMessage(reply).text, "Your current draft is unchanged.");
});

test("posting is shown as unavailable without a draft or fake publishing UI", () => {
  const text = "Job posting by chat instruction is not available. Review a draft and use its Publish to Discord button.";
  const message = replyToChatMessage({status: "unsupported", intent: "unsupported", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: text});
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message}));
  assert.ok(html.includes(text));
  assert.ok(!html.includes("chat-draft"));
});


test("draft action footer has publish and revise buttons", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json(result()));
  const message=replyToChatMessage(await sendRecruiterMessage("Create a JD."));
  const html=renderToStaticMarkup(createElement(ChatMessageView,{message,onPublish:()=>{},onRevise:()=>{}}));
  assert.match(html,/Publish to Discord/);
  assert.match(html,/Revise draft/);
  assert.match(html,/Policy grounded/);
  assert.match(html,/<details class="grounding-section"/);
});

test("publication request maps only circular fields and optional context to backend", async (t) => {
  let calls=0;
  const draft=result().job_description_result;
  // Validate through the existing runtime contract before the publish action.
  t.mock.method(globalThis,"fetch",async () => Response.json(result()));
  const response=await sendRecruiterMessage("Create a JD.");
  if(response.status!=="jd_generated") assert.fail("Expected draft");
  t.mock.restoreAll();
  t.mock.method(globalThis,"fetch",async (url,options) => {
    calls++;
    assert.equal(url,"/api/v1/recruiter-chat/publish");
    const body=JSON.parse(String(options?.body));
    assert.deepEqual(body,{title:draft.job_description.title,summary:draft.job_description.summary,responsibilities:draft.job_description.responsibilities,required_skills:draft.job_description.required_skills,preferred_skills:draft.job_description.preferred_skills,qualifications:draft.job_description.qualifications,location:"Dhaka",employment_type:"full_time",work_arrangement:"on_site"});
    return Response.json({destination:"discord",status:"published",external_id:"123456789012345678"});
  });
  const metadata=await publishDraft(response.job_description_result,{location:"Dhaka",employment_type:"full_time",work_arrangement:"on_site"});
  assert.equal(metadata.external_id,"123456789012345678");
  assert.equal(calls,1);
});

test("publication failures are sanitized and never automatically retried", async (t) => {
  t.mock.method(globalThis,"fetch",async () => Response.json(result()));
  const response=await sendRecruiterMessage("Create a JD.");
  if(response.status!=="jd_generated") assert.fail("Expected draft");
  for (const status of [422,502,503,504]) {
    let calls=0;
    t.mock.method(globalThis,"fetch",async()=> { calls++; return Response.json({message:"PRIVATE_SECRET"},{status}); });
    await assert.rejects(publishDraft(response.job_description_result),(error:Error)=>!error.message.includes("PRIVATE_SECRET"));
    assert.equal(calls,1);
  }
});

test("malformed confirmation is rejected rather than showing success", async (t) => {
  t.mock.method(globalThis,"fetch",async () => Response.json(result()));
  const response=await sendRecruiterMessage("Create a JD.");
  if(response.status!=="jd_generated") assert.fail("Expected draft");
  t.mock.method(globalThis,"fetch",async()=>Response.json({destination:"discord",status:"published",external_id:"bad"}));
  await assert.rejects(publishDraft(response.job_description_result));
});

test("draft card renders loading, confirmed metadata and safe failure states", async (t) => {
  t.mock.method(globalThis,"fetch",async () => Response.json(result()));
  const message=replyToChatMessage(await sendRecruiterMessage("Create a JD."));
  const loading=renderToStaticMarkup(createElement(ChatMessageView,{message:{...message,publication:{status:"loading"}},onPublish:()=>{},onRevise:()=>{}}));
  assert.match(loading,/Publishing/);
  assert.match(loading,/disabled/);
  const success=renderToStaticMarkup(createElement(ChatMessageView,{message:{...message,publication:{status:"success",result:{destination:"discord",status:"published",external_id:"123456789012345678"}}},onPublish:()=>{},onRevise:()=>{}}));
  for(const value of ["Publication confirmed","discord","published","123456789012345678"]) assert.ok(success.includes(value));
  assert.ok(!success.includes("has not been approved, saved, or published"));
  const failed=renderToStaticMarkup(createElement(ChatMessageView,{message:{...message,publication:{status:"failed",message:"Check Discord before another attempt."}},onPublish:()=>{},onRevise:()=>{}}));
  assert.match(failed,/role="alert"/);
  assert.match(failed,/Check Discord/);
  assert.match(failed,/disabled/);
});
