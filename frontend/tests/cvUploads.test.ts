import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { isCvUploadResponse, uploadCvs, validateCvSelection } from "../src/api/cvUploads.ts";
import { CvUploadConfirmation, SelectedCvFiles, WorkspaceNavigation, ScreeningWorkflowSteps, screeningPrerequisiteMessage } from "../src/components/cvIntakePresentation.ts";

const REFERENCE = "TT-JOB-30BB2CDF9A5CCCA9";
const BATCH = "9014cc92-9256-48e2-a5f7-52981251cc44";
const UPLOAD = "aa14cc92-9256-48e2-a5f7-52981251cc44";
function result() {
  return {status: "uploaded", job_reference: REFERENCE, batch_id: BATCH,
    accepted_count: 1, files: [{upload_id: UPLOAD, file_type: "pdf", size_bytes: 100}]};
}

test("PDF/DOCX selections and exactly 20 files pass usability validation", () => {
  assert.equal(validateCvSelection(REFERENCE, [{name: "synthetic.pdf", size: 100}, {name: "synthetic.DOCX", size: 200}]), null);
  assert.equal(validateCvSelection(REFERENCE, Array.from({length: 20}, () => ({name: "synthetic.pdf", size: 100}))), null);
});

test("invalid selection count, reference, type and size fail", () => {
  for (const files of [[], Array.from({length: 21}, () => ({name: "synthetic.pdf", size: 100})),
    [{name: "synthetic.exe", size: 100}], [{name: "synthetic.pdf", size: 0}],
    [{name: "synthetic.pdf", size: 10 * 1024 * 1024 + 1}],
    Array.from({length: 11}, () => ({name: "synthetic.pdf", size: 10 * 1024 * 1024}))]) {
    assert.ok(validateCvSelection(REFERENCE, files));
  }
  for (const reference of ["", "TT-JOB-0001", "../private", "tt-job-30bb2cdf9a5ccca9"]) {
    assert.ok(validateCvSelection(reference, [{name: "synthetic.pdf", size: 100}]));
  }
});

test("selected filenames render locally as escaped text with sizes and remove actions", () => {
  const html = renderToStaticMarkup(createElement(SelectedCvFiles, {
    files: [{name: "<script>synthetic.pdf", size: 1024}], disabled: false, onRemove: () => {},
  }));
  assert.match(html, /&lt;script&gt;synthetic.pdf/);
  assert.match(html, /1.0 KiB/);
  assert.match(html, /Remove/);
  assert.ok(!html.includes("<script>"));
});

test("upload success shows accepted count and opaque batch reference only", () => {
  const html = renderToStaticMarkup(createElement(CvUploadConfirmation, {result: result() as Parameters<typeof CvUploadConfirmation>[0]["result"]}));
  assert.match(html, /1 file stored/);
  assert.match(html, new RegExp(BATCH));
  assert.match(html, /no screening or scoring/);
  assert.ok(!html.includes("synthetic.pdf"));
  assert.ok(!html.includes("iframe"));
});

test("workspace navigation keeps JD Assistant available alongside CV Intake", () => {
  const html = renderToStaticMarkup(createElement(WorkspaceNavigation, {mode: "jd", onChange: () => {}}));
  assert.match(html, /JD Assistant/);
  assert.match(html, /CV Intake/);
  assert.match(html, /aria-pressed="true"/);
});

test("screening workflow progress reflects confirmed criteria, upload and results state", () => {
  const initial = renderToStaticMarkup(createElement(ScreeningWorkflowSteps, {hasSuggestions: false, hasSnapshot: false, hasBatch: false, isScreened: false}));
  assert.match(initial, /Review job criteria/);
  assert.match(initial, /not yet available/);
  const ready = renderToStaticMarkup(createElement(ScreeningWorkflowSteps, {hasSuggestions: true, hasSnapshot: true, hasBatch: true, isScreened: false}));
  assert.match(ready, /Screen candidates/);
  assert.match(ready, /is-current/);
  const complete = renderToStaticMarkup(createElement(ScreeningWorkflowSteps, {hasSuggestions: true, hasSnapshot: true, hasBatch: true, isScreened: true}));
  assert.equal((complete.match(/is-complete/g) ?? []).length, 4);
});

test("screening availability explains the actual missing prerequisite", () => {
  const defaults = {busy: false, hasSuggestions: true, hasBatch: true, hasSnapshot: true, referenceMatches: true};
  assert.equal(screeningPrerequisiteMessage({...defaults, busy: true}), "Wait for the current operation to finish.");
  assert.match(screeningPrerequisiteMessage({...defaults, hasSuggestions: false})!, /Generate a JD/);
  assert.match(screeningPrerequisiteMessage({...defaults, hasBatch: false})!, /Upload a CV batch/);
  assert.match(screeningPrerequisiteMessage({...defaults, hasSnapshot: false})!, /explicitly confirm/);
  assert.match(screeningPrerequisiteMessage({...defaults, referenceMatches: false})!, /Job Reference must match/);
  assert.equal(screeningPrerequisiteMessage(defaults), null);
});

test("multipart request sends original File objects without reading or encoding their contents", async t => {
  const file = new File(["synthetic file contents"], "synthetic.pdf", {type: "application/pdf"});
  t.mock.method(file, "text", async () => { assert.fail("Do not render or read CV text in the browser."); });
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/v1/cv-uploads");
    assert.equal(options?.method, "POST");
    assert.equal(options?.headers, undefined);
    assert.ok(options?.body instanceof FormData);
    assert.equal(options.body.get("job_reference"), REFERENCE);
    assert.equal(options.body.getAll("files").length, 1);
    assert.equal((options.body.get("files") as File).name, file.name);
    return Response.json(result(), {status: 201});
  });
  const response = await uploadCvs(REFERENCE, [file]);
  assert.equal(response.accepted_count, 1);
});

test("untrusted failure text is sanitized and no retry occurs", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json({code: "storage_failed", message: "PRIVATE_PATH_AND_CONTENT"}, {status: 500});
  });
  await assert.rejects(uploadCvs(REFERENCE, [new File(["synthetic"], "synthetic.pdf")]), (error: Error) => !error.message.includes("PRIVATE"));
  assert.equal(calls, 1);
});

test("unsafe or mismatched metadata cannot produce upload success", () => {
  assert.equal(isCvUploadResponse(result()), true);
  for (const response of [{...result(), path: "PRIVATE_PATH"}, {...result(), accepted_count: 2},
    {...result(), batch_id: "not-opaque"}, {...result(), job_reference: "../private"},
    {...result(), files: [{...result().files[0], filename: "PRIVATE_NAME"}]},
    {...result(), files: [{...result().files[0], file_type: ["pdf"]}]}]) {
    assert.equal(isCvUploadResponse(response), false);
  }
});
