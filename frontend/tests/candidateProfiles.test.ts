import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { extractCandidateProfiles, isCandidateProfilesResponse } from "../src/api/candidateProfiles.ts";
import { CandidateProfileAction, CandidateProfilesSummary } from "../src/components/candidateProfilesPresentation.ts";
import { WorkspaceNavigation } from "../src/components/cvIntakePresentation.ts";
import type { CandidateAttribute, CandidateProfilesResponse } from "../src/types/candidateProfile.ts";
import type { CvUploadResponse } from "../src/types/cvUpload.ts";
import type { CvExtractionResponse } from "../src/types/cvExtraction.ts";

const REFERENCE = "TT-JOB-30BB2CDF9A5CCCA9";
const BATCH = "9014cc92-9256-48e2-a5f7-52981251cc44";
const UPLOAD = "aa14cc92-9256-48e2-a5f7-52981251cc44";
const batch: CvUploadResponse = {status: "uploaded", job_reference: REFERENCE, batch_id: BATCH, accepted_count: 1,
  files: [{upload_id: UPLOAD, file_type: "pdf", size_bytes: 100}]};
function fact(value: string): CandidateAttribute { return {value, source: {kind: "page", number: 1, method: "digital", block_type: null}}; }
function result(): CandidateProfilesResponse {
  return {status: "processed", job_reference: REFERENCE, batch_id: BATCH, processed_count: 1, candidates: [{upload_id: UPLOAD, parsing_status: "parsed",
    contact: {candidate_name: fact("Synthetic Candidate"), emails: [fact("synthetic@example.invalid")], phones: [], links: [], location: null},
    qualifications: {education: [{institution: fact("Synthetic University"), qualification: fact("BSc"), field_of_study: null, date_or_period: null}],
      work_history: [{employer: fact("Example Labs"), role_title: fact("Backend Engineer"), date_or_period: null, location: null,
        responsibilities_or_achievements: [fact("Wrote automated tests")]}], skills: [fact("Python"), fact("FastAPI")]}}]};
}
function extraction(required: boolean): CvExtractionResponse {
  return {status: "processed", job_reference: REFERENCE, batch_id: BATCH, processed_count: 1,
    files: [{upload_id: UPLOAD, file_type: "pdf", extraction_status: required ? "ocr_required" : "text_extracted", text_char_count: 100,
      source_unit_count: 1, ocr_recommended: required}]};
}

test("profile action follows digital extraction and OCR attempt, with disabled loading", () => {
  const props = {extraction: extraction(false), ocrAttempted: false, busy: false, parsing: false, onParse: () => {}};
  assert.match(renderToStaticMarkup(createElement(CandidateProfileAction, props)), /Extract candidate profiles/);
  assert.equal(renderToStaticMarkup(createElement(CandidateProfileAction, {...props, extraction: null})), "");
  assert.equal(renderToStaticMarkup(createElement(CandidateProfileAction, {...props, extraction: extraction(true)})), "");
  assert.match(renderToStaticMarkup(createElement(CandidateProfileAction, {...props, extraction: extraction(true), ocrAttempted: true})), /Extract candidate profiles/);
  const loading = renderToStaticMarkup(createElement(CandidateProfileAction, {...props, busy: true, parsing: true}));
  assert.match(loading, /Extracting candidate profiles/); assert.match(loading, /disabled/);
  assert.match(loading, /Sends CV-derived text to Groq/);
});

test("parsed profiles show contact, education, work and skills with safe locators", () => {
  const response = result();
  response.candidates[0].qualifications!.education[0].institution!.source = {kind: "block", number: 4, method: "digital", block_type: "paragraph"};
  response.candidates[0].qualifications!.skills[1].source = {kind: "page", number: 2, method: "ocr", block_type: null};
  const html = renderToStaticMarkup(createElement(CandidateProfilesSummary, {result: response}));
  for (const text of ["Contact", "Education", "Work history", "Skills", "Synthetic Candidate", "Synthetic University", "Backend Engineer", "Python", "Page 1", "Block 4", "Page 2 · OCR"]) assert.ok(html.includes(text));
  assert.match(html, /not a suitability decision/);
});

test("source-unavailable and parsing-failed states are distinct from rejection", () => {
  for (const status of ["source_unavailable", "parsing_failed"] as const) {
    const response = result(); response.candidates[0] = {...response.candidates[0], parsing_status: status, contact: null, qualifications: null};
    const html = renderToStaticMarkup(createElement(CandidateProfilesSummary, {result: response}));
    assert.match(html, status === "source_unavailable" ? /Source unavailable/ : /Parsing failed/);
    assert.ok(!html.includes("Synthetic Candidate"));
  }
});

test("raw CV/evidence is not rendered, markup is escaped, JD navigation remains", () => {
  const response = result(); response.candidates[0].contact!.candidate_name!.value = "<script>Synthetic</script>";
  const html = renderToStaticMarkup(createElement(CandidateProfilesSummary, {result: {...response, text: "PRIVATE_CV", evidence: "PRIVATE_QUOTE"}}));
  assert.ok(!html.includes("PRIVATE_CV") && !html.includes("PRIVATE_QUOTE") && !html.includes("<script>"));
  assert.match(html, /&lt;script&gt;/);
  assert.match(renderToStaticMarkup(createElement(WorkspaceNavigation, {mode: "cv", onChange: () => {}})), /JD Assistant/);
});

test("candidate request sends only stored identity with no provider options or retry", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls++; assert.equal(url, `/api/v1/cv-uploads/${REFERENCE}/${BATCH}/candidate-profiles`);
    assert.equal(options?.method, "POST"); assert.equal(options?.body, undefined);
    return Response.json(result());
  });
  assert.deepEqual(await extractCandidateProfiles(batch), result()); assert.equal(calls, 1);
});

test("public profile validation forbids evidence, scores and contact in qualifications", () => {
  assert.equal(isCandidateProfilesResponse(result()), true);
  for (const modify of [
    (response: CandidateProfilesResponse) => ({...response, text: "PRIVATE"}),
    (response: CandidateProfilesResponse) => ({...response, candidates: [{...response.candidates[0], score: 99}]}),
    (response: CandidateProfilesResponse) => ({...response, candidates: [{...response.candidates[0], qualifications: {...response.candidates[0].qualifications, email: "PRIVATE"}}]}),
    (response: CandidateProfilesResponse) => ({...response, candidates: [{...response.candidates[0], contact: {...response.candidates[0].contact, candidate_name: {...fact("Synthetic"), evidence: "PRIVATE"}}}]}),
  ]) assert.equal(isCandidateProfilesResponse(modify(result())), false);
});

test("unrelated IDs and untrusted provider errors cannot become displayed profiles", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({...result(), batch_id: UPLOAD}));
  await assert.rejects(extractCandidateProfiles(batch), /invalid confirmation/);
  t.mock.method(globalThis, "fetch", async () => Response.json({code: "candidate_parser_not_configured", message: "PRIVATE_KEY"}, {status: 503}));
  await assert.rejects(extractCandidateProfiles(batch), {message: "Candidate profile extraction is not configured on this server."});
});
