import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { extractCvs, isCvExtractionResponse } from "../src/api/cvExtraction.ts";
import { CvExtractionSummary, CvUploadConfirmation, WorkspaceNavigation } from "../src/components/cvIntakePresentation.ts";
import type { CvExtractionResponse } from "../src/types/cvExtraction.ts";
import type { CvUploadResponse } from "../src/types/cvUpload.ts";

const REFERENCE = "TT-JOB-30BB2CDF9A5CCCA9";
const BATCH = "9014cc92-9256-48e2-a5f7-52981251cc44";
const IDS = ["aa14cc92-9256-48e2-a5f7-52981251cc44", "bb14cc92-9256-48e2-a5f7-52981251cc44", "cc14cc92-9256-48e2-a5f7-52981251cc44"];
const batch: CvUploadResponse = {status: "uploaded", job_reference: REFERENCE, batch_id: BATCH, accepted_count: 3,
  files: IDS.map((upload_id, index) => ({upload_id, file_type: index === 1 ? "docx" : "pdf", size_bytes: 100}))};
function result(): CvExtractionResponse {
  return {status: "processed", job_reference: REFERENCE, batch_id: BATCH, processed_count: 3, files: [
    {upload_id: IDS[0], file_type: "pdf", extraction_status: "text_extracted", text_char_count: 1000, source_unit_count: 2, ocr_recommended: false},
    {upload_id: IDS[1], file_type: "docx", extraction_status: "text_extracted", text_char_count: 500, source_unit_count: 18, ocr_recommended: false},
    {upload_id: IDS[2], file_type: "pdf", extraction_status: "ocr_required", text_char_count: 0, source_unit_count: 1, ocr_recommended: true},
  ]};
}

test("uploaded batch offers Extract text action and disabled loading state", () => {
  const html = renderToStaticMarkup(createElement(CvUploadConfirmation, {result: batch, onExtract: () => {}, extracting: false}));
  assert.match(html, /Extract text/);
  const loading = renderToStaticMarkup(createElement(CvUploadConfirmation, {result: batch, onExtract: () => {}, extracting: true}));
  assert.match(loading, /Extracting text/);
  assert.match(loading, /disabled/);
});

test("mixed extraction status shows pages, blocks and explicit unimplemented OCR", () => {
  const html = renderToStaticMarkup(createElement(CvExtractionSummary, {result: result()}));
  assert.match(html, /3 CVs processed/);
  assert.match(html, /PDF · <\/strong>Text extracted · 2 pages/);
  assert.match(html, /DOCX · <\/strong>Text extracted · 18 blocks/);
  assert.match(html, /OCR required/);
  assert.match(html, /Digital text was insufficient. OCR processing is not implemented yet./);
  assert.ok(!html.includes("text_char_count"));
});

test("failed extraction is not shown as missing qualifications", () => {
  const response = result();
  response.files[2] = {...response.files[2], extraction_status: "extraction_failed", ocr_recommended: false};
  const html = renderToStaticMarkup(createElement(CvExtractionSummary, {result: response}));
  assert.match(html, /Extraction failed/);
  assert.match(html, /not evidence of missing qualifications/);
});

test("presentation renders metadata only and keeps JD Assistant accessible", () => {
  const response = {...result(), text: "SYNTHETIC_PRIVATE_TEXT"};
  const html = renderToStaticMarkup(createElement(CvExtractionSummary, {result: response}));
  assert.ok(!html.includes("SYNTHETIC_PRIVATE_TEXT"));
  assert.match(renderToStaticMarkup(createElement(WorkspaceNavigation, {mode: "cv", onChange: () => {}})), /JD Assistant/);
});

test("batch request uses IDs only and validates matching upload metadata", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls++;
    assert.equal(url, `/api/v1/cv-uploads/${REFERENCE}/${BATCH}/extract`);
    assert.equal(options?.method, "POST");
    assert.equal(options?.body, undefined);
    return Response.json(result());
  });
  assert.deepEqual(await extractCvs(batch), result());
  assert.equal(calls, 1);
});

test("raw text, inconsistent statuses and unrelated batch data cannot enter component state", () => {
  assert.equal(isCvExtractionResponse(result()), true);
  for (const response of [{...result(), text: "PRIVATE"}, {...result(), processed_count: 4},
    {...result(), files: [{...result().files[0], text: "PRIVATE"}]},
    {...result(), files: result().files.map(file => ({...file, ocr_recommended: true}))},
    {...result(), files: [...result().files.slice(0, 2), {...result().files[2], file_type: "docx"}]},
    {...result(), files: [result().files[0], result().files[0], result().files[0]]}]) {
    assert.equal(isCvExtractionResponse(response), false);
  }
});

test("provider/parser failure details remain sanitized and no retry occurs", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json({message: "PRIVATE_PATH_OR_TEXT"}, {status: 500});
  });
  await assert.rejects(extractCvs(batch), (error: Error) => !error.message.includes("PRIVATE"));
  assert.equal(calls, 1);
});

test("unrelated batch and upload IDs are rejected", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({...result(), batch_id: IDS[0]}));
  await assert.rejects(extractCvs(batch), /invalid confirmation/);
});
