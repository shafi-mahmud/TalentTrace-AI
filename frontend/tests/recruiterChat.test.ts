import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { isValidRecruiterMessage, sendRecruiterMessage } from "../src/api/recruiterChat.ts";
import { ChatMessageView, RecruiterChatPage, replyToChatMessage } from "../src/components/chatPresentation.ts";

function result() {
  return {
    status: "jd_generated", intent: "create_job_description", assistant_message: "Your draft is ready. Human review required.",
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
  t.mock.method(globalThis, "fetch", async () => Response.json({ status: "clarification", intent: "create_job_description", assistant_message: "Please include responsibilities and skills.", missing_fields: ["responsibilities", "required_skills"] }));
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
  t.mock.method(globalThis, "fetch", async () => Response.json({ status: "unsupported", intent: "unsupported", assistant_message: "Only JD creation is available." }));
  assert.equal((await sendRecruiterMessage("Publish a job." )).status, "unsupported");
});

test("unsafe server error text is never shown", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ message: "PRIVATE_SECRET" }, { status: 502 }));
  await assert.rejects(sendRecruiterMessage("Create a JD."), (error: Error) => !error.message.includes("PRIVATE_SECRET"));
});


test("multiline job instructions and comparisons pass the submission guard", () => {
  assert.equal(isValidRecruiterMessage("Create a JD.\r\nSkills:\tPython >= 3.11"), true);
  assert.equal(isValidRecruiterMessage("Build transcript/resume processing services"), true);
  for (const text of ["", "x".repeat(4001), "unsafe\x00", "unsafe\x1b", "unsafe\u202e"]) {
    assert.equal(isValidRecruiterMessage(text), false);
  }
});

test("optional evidence clarification uses public field labels", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({status: "clarification", intent: "create_job_description", assistant_message: "Clarify work arrangement and experience; resend the complete instruction.", missing_fields: ["work_arrangement", "minimum_experience_years"]}));
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
  assert.match(html, /has not been approved, saved, or published/);
});

test("clarification maps directly into an assistant conversation message", () => {
  const message = replyToChatMessage({status: "clarification", intent: "create_job_description", assistant_message: "Please include skills.", missing_fields: ["required_skills"]});
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message}));
  assert.match(html, /chat-assistant/);
  assert.match(html, /Required skills/);
  assert.ok(!html.includes("chat-draft"));
});

test("posting is shown as unavailable without a draft or fake publishing UI", () => {
  const text = "Job posting is not available in this chatbot yet. I can currently help create a job description draft only.";
  const message = replyToChatMessage({status: "unsupported", intent: "unsupported", assistant_message: text});
  const html = renderToStaticMarkup(createElement(ChatMessageView, {message}));
  assert.ok(html.includes(text));
  assert.ok(!html.includes("chat-draft"));
});
