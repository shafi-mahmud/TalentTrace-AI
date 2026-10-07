import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { isCvOcrResponse, runCvOcr } from "../src/api/cvOcr.ts";
import { CvExtractionSummary, CvOcrSummary, WorkspaceNavigation } from "../src/components/cvIntakePresentation.ts";
import type { CvExtractionResponse } from "../src/types/cvExtraction.ts";
import type { CvOcrResponse } from "../src/types/cvOcr.ts";

const REFERENCE = "TT-JOB-30BB2CDF9A5CCCA9";
const BATCH = "9014cc92-9256-48e2-a5f7-52981251cc44";
const UPLOAD = "aa14cc92-9256-48e2-a5f7-52981251cc44";
function extracted(): CvExtractionResponse {
  return {status: "processed", job_reference: REFERENCE, batch_id: BATCH, processed_count: 1,
    files: [{upload_id: UPLOAD, file_type: "pdf", extraction_status: "ocr_required", text_char_count: 0, source_unit_count: 2, ocr_recommended: true}]};
}
function result(): CvOcrResponse {
  return {status: "processed", job_reference: REFERENCE, batch_id: BATCH, attempted_count: 1,
    files: [{upload_id: UPLOAD, ocr_status: "ocr_extracted", text_char_count: 1000, page_count: 2, ocr_page_count: 2}]};
}

test("OCR action appears only when required and disables during processing", () => {
  assert.match(renderToStaticMarkup(createElement(CvExtractionSummary, {result: extracted(), onOcr: () => {}})), /Run OCR/);
  const loading = renderToStaticMarkup(createElement(CvExtractionSummary, {result: extracted(), onOcr: () => {}, processingOcr: true}));
  assert.match(loading, /Running OCR/); assert.match(loading, /disabled/);
  const digital = extracted();
  digital.files[0] = {...digital.files[0], extraction_status: "text_extracted", text_char_count: 1000, ocr_recommended: false};
  assert.ok(!renderToStaticMarkup(createElement(CvExtractionSummary, {result: digital, onOcr: () => {}})).includes("Run OCR"));
});

test("OCR success and prior digital stage remain visible as metadata", () => {
  const html = renderToStaticMarkup(createElement(CvOcrSummary, {result: result()}));
  assert.match(html, /OCR extracted · 2 pages/); assert.match(html, /Extraction evidence only/);
  assert.match(renderToStaticMarkup(createElement(CvExtractionSummary, {result: extracted()})), /OCR required/);
});

test("OCR failure and no-op states do not imply absent qualifications", () => {
  const failed = result(); failed.files[0] = {...failed.files[0], ocr_status: "ocr_failed", text_char_count: 0};
  const html = renderToStaticMarkup(createElement(CvOcrSummary, {result: failed}));
  assert.match(html, /OCR failed/); assert.match(html, /not evidence of missing qualifications/);
  assert.match(renderToStaticMarkup(createElement(CvOcrSummary, {result: {...result(), attempted_count: 0, files: []}})), /No PDFs required OCR/);
});

test("OCR presentation omits recognized text and keeps JD navigation", () => {
  assert.ok(!renderToStaticMarkup(createElement(CvOcrSummary, {result: {...result(), text: "PRIVATE_OCR_TEXT"}})).includes("PRIVATE_OCR_TEXT"));
  assert.match(renderToStaticMarkup(createElement(WorkspaceNavigation, {mode: "cv", onChange: () => {}})), /JD Assistant/);
});

test("OCR request submits batch identity only and accepts matching metadata", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls++; assert.equal(url, `/api/v1/cv-uploads/${REFERENCE}/${BATCH}/ocr`);
    assert.equal(options?.method, "POST"); assert.equal(options?.body, undefined);
    return Response.json(result());
  });
  assert.deepEqual(await runCvOcr(extracted()), result()); assert.equal(calls, 1);
});

test("OCR-not-configured is controlled without paths or retry", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++; return Response.json({code: "ocr_not_configured", message: "PRIVATE_TESSDATA_PATH"}, {status: 503});
  });
  await assert.rejects(runCvOcr(extracted()), {message: "OCR is not configured on this server."});
  assert.equal(calls, 1);
});

test("untrusted errors and mismatched confirmations are rejected", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({message: "PRIVATE_TEXT"}, {status: 500}));
  await assert.rejects(runCvOcr(extracted()), (error: Error) => !error.message.includes("PRIVATE"));
  t.mock.method(globalThis, "fetch", async () => Response.json({...result(), batch_id: UPLOAD}));
  await assert.rejects(runCvOcr(extracted()), /invalid confirmation/);
});

test("OCR validation forbids text, paths, invalid counts and statuses", () => {
  assert.equal(isCvOcrResponse(result()), true);
  assert.equal(isCvOcrResponse({...result(), attempted_count: 0, files: []}), true);
  for (const body of [{...result(), text: "PRIVATE"}, {...result(), attempted_count: 0},
    {...result(), files: [{...result().files[0], tessdata: "PRIVATE_PATH"}]},
    {...result(), files: [{...result().files[0], ocr_page_count: 3}]},
    {...result(), files: [{...result().files[0], ocr_status: "text_extracted"}]},
    {...result(), files: [{...result().files[0], text_char_count: 0}]},
    {...result(), attempted_count: 2, files: [result().files[0], result().files[0]]}]) assert.equal(isCvOcrResponse(body), false);
});

test("OCR confirmation cannot attribute a result to another upload", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({...result(), files: [{...result().files[0], upload_id: BATCH}]}));
  await assert.rejects(runCvOcr(extracted()), /invalid confirmation/);
});
