import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { screenCvBatch, isBatchScreeningResponse, isReviewedSnapshot, isScreeningSuggestions } from "../src/api/screening.ts";
import { ScreeningResults } from "../src/components/screeningPresentation.ts";
import ScreeningCriteriaReview, { confirmReviewedCriteria, CriteriaEditor } from "../src/components/ScreeningCriteriaReview.ts";
import { isRecruiterChatResponse } from "../src/api/recruiterChat.ts";
import type { BatchScreeningResponse, ReviewedJobSnapshot } from "../src/types/screening.ts";
import type { CvUploadResponse } from "../src/types/cvUpload.ts";

const reference = "TT-JOB-0123456789ABCDEF";
const id = "9014cc92-9256-48e2-a5f7-52981251cc44";
const batchId = "12345678-1234-4234-8234-123456789abc";
const snapshot: ReviewedJobSnapshot = {job_reference: reference, job_title: "Backend Engineer", criteria_confirmed: true,
  criteria: [{criterion_id: "python", description: "Python", category: "skill", is_hard: true}]};
const batch: CvUploadResponse = {status: "uploaded", job_reference: reference, batch_id: batchId, accepted_count: 1,
  files: [{upload_id: id, file_type: "pdf", size_bytes: 200}]};
function result(): BatchScreeningResponse {
  return {status: "processed", job_reference: reference, batch_id: batchId, snapshot: structuredClone(snapshot), processed_count: 1,
    ranking: [{upload_id: id, rank: 1, tied: false, supported_count: 1, ambiguous_count: 0, not_found_count: 0, total_requirements: 1}],
    candidates: [{upload_id: id, error_code: null, overall_coverage: "met", result: {job_reference: reference, upload_id: id, status: "decision_complete",
      screening_decision: "eligible", unmet_hard_requirement_ids: [], ambiguous_hard_requirement_ids: [], exclusion_reasons: [],
      matching_result: {job_reference: reference, upload_id: id, parsing_status: "parsed", status: "matching_complete", error_code: null,
        screening_decision: null, requirement_context: {skill_ids: ["python"], experience_ids: [], education_ids: [], hard_requirement_ids: ["python"]},
        matches: [{criterion_id: "python", match_status: "supported", match_method: "semantic", explanation: "Referenced evidence supports this requirement.",
          evidence: [{fact_id: "fact:0001", value: "Built APIs using Django", source: {kind: "page", number: 2, method: "ocr", block_type: null}}]}]}}}]};
}

test("review snapshot requires explicit confirmation, bounded criteria and valid reference", () => {
  assert.ok(isReviewedSnapshot(snapshot));
  for (const value of [false, "true", 1, null, undefined]) assert.ok(!isReviewedSnapshot({...snapshot, criteria_confirmed: value}));
  assert.ok(!isReviewedSnapshot({...snapshot, job_reference: "Other"}));
  assert.ok(!isReviewedSnapshot({...snapshot, candidates: []}));
  assert.ok(!isReviewedSnapshot({...snapshot, criteria: [...snapshot.criteria, {...snapshot.criteria[0], criterion_id: "PYTHON"}]}));
  assert.ok(!isReviewedSnapshot({...snapshot, criteria: [{...snapshot.criteria[0], is_hard: "true"}]}));
  assert.ok(!isReviewedSnapshot({...snapshot, criteria: [{...snapshot.criteria[0], description: " \n "}]}));
});

test("source-backed suggestions are not approved snapshots", () => {
  const suggestions = {job_title: snapshot.job_title, criteria: snapshot.criteria.map(c => ({...c, is_hard: false}))};
  assert.ok(isScreeningSuggestions(suggestions));
  assert.ok(!isReviewedSnapshot(suggestions));
  assert.ok(!isScreeningSuggestions({...suggestions, criteria: [{...suggestions.criteria[0], category: "configuration"}]}));
});

test("review panel exposes descriptions/categories/flags and starts unconfirmed", () => {
  const suggestions = {job_title: snapshot.job_title, criteria: snapshot.criteria.map(c => ({...c, is_hard: false}))};
  const html = renderToStaticMarkup(createElement(ScreeningCriteriaReview, {suggestions, criteria: suggestions.criteria,
    sources: [], reviewed: false, jobReference: reference, disabled: false,
    onConfirm: () => assert.fail("Rendering must not approve"), onChange: () => {}, onReviewedChange: () => {}}));
  for (const label of ["Review screening criteria", "Awaiting your review", "Category", "Requirement type", "Python", "Confirmation does not approve"]) assert.ok(html.includes(label));
  assert.match(html, /value="preferred" selected/);
  assert.match(html, /Confirm requirements/);
  assert.ok(!html.includes('type="checkbox"'));
  assert.ok(!html.includes('checked=""'));
  assert.equal(confirmReviewedCriteria(suggestions, reference, suggestions.criteria, false), null);
  const confirmed = confirmReviewedCriteria(suggestions, reference, suggestions.criteria, true)!;
  assert.equal(confirmed.job_reference, reference);
  assert.equal(confirmed.criteria[0].is_hard, false);
  suggestions.criteria[0].description = "Changed";
  assert.equal(confirmed.criteria[0].description, "Python");
  assert.equal(confirmReviewedCriteria(suggestions, "OTHER", suggestions.criteria, true), null);
});

test("manual criteria editor clearly labels recruiter-entered criteria as not policy-backed", () => {
  const html = renderToStaticMarkup(createElement(ScreeningCriteriaReview, {suggestions: {job_title: "Backend Engineer", criteria: []},
    criteria: [], sources: [], reviewed: false, origin: "manual", jobReference: reference, disabled: false,
    onConfirm: () => {}, onChange: () => {}, onReviewedChange: () => {}}));
  assert.match(html, /Recruiter-entered criteria/);
  assert.match(html, /not policy-backed/);
  assert.match(html, /Confirm requirements/);
});

test("changing a manual requirement updates its flag and clears prior confirmation", () => {
  const criterion = {criterion_id: "manual-python", description: "Python", category: "skill" as const, is_hard: false};
  let updated = [criterion];
  let reviewed = true;
  const tree = CriteriaEditor({criteria: [criterion], sources: [], reviewed, disabled: false, origin: "manual",
    onChange: value => {updated = value;}, onReviewedChange: value => {reviewed = value;}});
  const sectionChildren = tree.props.children as React.ReactElement[];
  const fieldset = sectionChildren[2];
  const rowChildren = fieldset.props.children[1].props.children as React.ReactElement[];
  const requirementTypeSelect = rowChildren[2].props.children[1];
  requirementTypeSelect.props.onChange({target: {value: "mandatory"}});
  assert.equal(updated[0].is_hard, true);
  assert.equal(reviewed, false);
});

test("screening submits reviewed snapshot and stored identity only", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls++;
    assert.equal(url, `/api/v1/cv-uploads/${reference}/${batchId}/screen`);
    assert.deepEqual(JSON.parse(String(options?.body)), snapshot);
    return Response.json(result());
  });
  assert.ok(isBatchScreeningResponse(await screenCvBatch(batch, snapshot)));
  assert.equal(calls, 1);
});

test("wrong job reference or unconfirmed snapshot cannot invoke backend", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {calls++; return Response.json(result());});
  await assert.rejects(screenCvBatch(batch, {...snapshot, job_reference: "TT-JOB-FFFFFFFFFFFFFFFF"}));
  await assert.rejects(screenCvBatch(batch, {...snapshot, criteria_confirmed: false} as unknown as ReviewedJobSnapshot));
  assert.equal(calls, 0);
});

test("response validation rejects wrong identity, verdict, evidence and criteria", () => {
  for (const mutate of [
    (r: BatchScreeningResponse) => {r.job_reference = "TT-JOB-FFFFFFFFFFFFFFFF";},
    (r: BatchScreeningResponse) => {r.candidates[0].result!.screening_decision = "excluded";},
    (r: BatchScreeningResponse) => {r.candidates[0].result!.matching_result.matches[0].evidence = [];},
    (r: BatchScreeningResponse) => {r.candidates[0].result!.matching_result.requirement_context.hard_requirement_ids = [];},
    (r: BatchScreeningResponse) => {r.candidates[0].result!.matching_result.matches[0].evidence[0].source.number = 0;},
    (r: BatchScreeningResponse) => {r.candidates.push(r.candidates[0]); r.processed_count++;},
  ]) {const value = result(); mutate(value); assert.ok(!isBatchScreeningResponse(value));}
});

test("response must match requested batch, upload set and exact reviewed snapshot", async t => {
  for (const mutate of [
    (r: BatchScreeningResponse) => {r.batch_id = id;},
    (r: BatchScreeningResponse) => {r.snapshot.job_title = "Other job";},
    (r: BatchScreeningResponse) => {r.snapshot.criteria[0].description = "Different requirement";},
  ]) {
    const response = result(); mutate(response);
    t.mock.method(globalThis, "fetch", async () => Response.json(response));
    await assert.rejects(screenCvBatch(batch, snapshot), /invalid confirmation/);
  }
});

test("public errors are fixed, sanitized and not retried", async t => {
  for (const status of [409, 422, 500, 503]) {
    let calls = 0;
    t.mock.method(globalThis, "fetch", async () => {calls++; return Response.json({message: "PRIVATE_SECRET_PATH"}, {status});});
    await assert.rejects(screenCvBatch(batch, snapshot), (error: Error) => !error.message.includes("PRIVATE_SECRET"));
    assert.equal(calls, 1);
  }
});

test("results render outcome, mandatory requirement and semantic OCR evidence separately from contact", () => {
  const html = renderToStaticMarkup(createElement(ScreeningResults, {result: result()}));
  for (const text of ["Eligible", "Python", "Mandatory", "semantic", "Built APIs using Django", "Page 2", "OCR", "Human review required", "Session-only"]) assert.ok(html.includes(text));
  assert.ok(!html.includes("Contact") && !html.includes("Email"));
});

test("exclusion and ambiguity retain evidence and never show as eligibility", () => {
  for (const status of ["not_found", "ambiguous"] as const) {
    const value = result(), row = value.candidates[0].result!;
    value.ranking = [];
    value.candidates[0].overall_coverage = status === "not_found" ? "unmet" : "uncertain";
    row.matching_result.matches[0].match_status = status;
    if (status === "not_found") {
      row.matching_result.matches[0].evidence = [];
      row.screening_decision = "excluded"; row.unmet_hard_requirement_ids = ["python"];
      row.exclusion_reasons = [{criterion_id: "python", code: "hard_requirement_not_demonstrated", message: "Hard requirement was not demonstrated in the parsed CV."}];
    } else {row.screening_decision = "insufficient_evidence"; row.ambiguous_hard_requirement_ids = ["python"];}
    assert.ok(isBatchScreeningResponse(value));
    const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
    assert.ok(html.includes(status === "not_found" ? "Excluded" : "Needs review"));
    assert.ok(!html.includes("Rank 1"));
  }
});

test("candidate processing failure is visible and has no exclusion verdict", () => {
  const value = result(); value.ranking = []; value.candidates[0].overall_coverage = "not_evaluated"; value.candidates[0].result = null; value.candidates[0].error_code = "screening_processing_failed";
  assert.ok(isBatchScreeningResponse(value));
  const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
  assert.ok(html.includes("Processing failed") && html.includes("no candidate decision"));
  assert.ok(!html.includes("outcome-excluded"));
});

test("provider and source failure remain non-decisions", () => {
  for (const status of ["matching_failed", "source_unavailable"] as const) {
    const value = result(), row = value.candidates[0].result!;
    value.ranking = [];
    value.candidates[0].overall_coverage = "not_evaluated";
    row.status = status; row.screening_decision = null;
    row.matching_result.status = status; row.matching_result.matches = [];
    row.matching_result.parsing_status = status === "source_unavailable" ? "parsing_failed" : "parsed";
    row.matching_result.error_code = status === "matching_failed" ? "semantic_provider_failed" : null;
    assert.ok(isBatchScreeningResponse(value));
    const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
    assert.ok(html.includes("no candidate decision") && !html.includes("outcome-excluded"));
  }
});

test("React escapes evidence and job text rather than interpreting markup", () => {
  const value = result(); value.snapshot.job_title = "<script>demo</script>";
  value.candidates[0].result!.matching_result.matches[0].evidence[0].value = "<img src=x onerror=alert(1)>";
  const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
  assert.ok(html.includes("&lt;script&gt;") && html.includes("&lt;img"));
  assert.ok(!html.includes("<script>") && !html.includes("<img "));
});

test("unsupported chat behavior remains unchanged", () => {
  assert.ok(isRecruiterChatResponse({status: "unsupported", intent: "unsupported", conversation_id: "6f6f6a5f-66a2-4e0e-8eb4-2f83d0d29910", assistant_message: "Use the draft action."}));
});

test("overall candidate coverage validates all evidence statuses and renders separately", () => {
  for (const [statuses, coverage, label] of [
    [["supported", "supported", "supported"], "met", "Met"],
    [["supported", "not_found", "not_found"], "partially_met", "Partially met"],
    [["not_found", "not_found", "not_found"], "unmet", "Unmet"],
    [["supported", "ambiguous", "not_found"], "uncertain", "Uncertain"],
  ] as const) {
    const value = result(), row = value.candidates[0].result!;
    value.snapshot.criteria = statuses.map((_, i) => ({criterion_id: `c${i}`, description: `Skill ${i}`, category: "skill", is_hard: false}));
    row.matching_result.requirement_context.skill_ids = ["c0", "c1", "c2"];
    row.matching_result.requirement_context.hard_requirement_ids = [];
    const template = row.matching_result.matches[0];
    row.matching_result.matches = statuses.map((status, i) => ({...structuredClone(template), criterion_id: `c${i}`,
      match_status: status, evidence: status === "not_found" ? [] : structuredClone(template.evidence)}));
    value.candidates[0].overall_coverage = coverage;
    Object.assign(value.ranking[0], {supported_count: statuses.filter(s => s === "supported").length,
      ambiguous_count: statuses.filter(s => s === "ambiguous").length, not_found_count: statuses.filter(s => s === "not_found").length, total_requirements: 3});
    assert.ok(isBatchScreeningResponse(value));
    const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
    assert.ok(html.includes(`Overall requirement coverage: ${label}`) && html.includes("Eligible"));
    if (coverage === "unmet") assert.ok(html.includes("not demonstrated in the CV"));
    value.candidates[0].overall_coverage = "not_evaluated";
    assert.ok(!isBatchScreeningResponse(value));
  }
  const failed = result(); failed.ranking = []; failed.candidates[0] = {upload_id: id, result: null,
    error_code: "screening_processing_failed", overall_coverage: "not_evaluated"};
  assert.ok(isBatchScreeningResponse(failed));
  assert.ok(renderToStaticMarkup(createElement(ScreeningResults, {result: failed})).includes("Overall requirement coverage: Not evaluated"));
});

test("ranking displays explicit ties in server order with expandable provenance", () => {
  const value = result();
  const otherId = "12345678-1234-4234-8234-123456789abc";
  const other = structuredClone(value.candidates[0]);
  other.upload_id = otherId; other.result!.upload_id = otherId; other.result!.matching_result.upload_id = otherId;
  value.candidates.push(other); value.processed_count = 2;
  value.ranking[0].tied = true;
  value.ranking.unshift({...value.ranking[0], upload_id: otherId});
  assert.ok(isBatchScreeningResponse(value));
  const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
  assert.equal((html.match(/Rank 1/g) ?? []).length, 2);
  assert.equal((html.match(/Tied/g) ?? []).length, 2);
  assert.ok(html.indexOf("Upload 2") < html.indexOf("Upload 1"));
  assert.ok(html.includes("1 of 1 requirements supported") && html.includes("<details") && html.includes("OCR"));
  assert.ok(!html.includes("Partially Met") && !html.includes("100"));
  value.ranking.reverse();
  assert.ok(!isBatchScreeningResponse(value));
});

test("zero-support eligible candidates retain separate ambiguous and not-found counts", () => {
  const value = result(), row = value.candidates[0].result!;
  value.snapshot.criteria[0].is_hard = false;
  row.matching_result.requirement_context.hard_requirement_ids = [];
  row.matching_result.matches[0].match_status = "ambiguous";
  value.candidates[0].overall_coverage = "uncertain";
  value.ranking[0].supported_count = 0; value.ranking[0].ambiguous_count = 1;
  assert.ok(isBatchScreeningResponse(value));
  let html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
  assert.ok(html.includes("0 of 1 requirements supported") && html.includes("1 ambiguous"));
  row.matching_result.matches[0].match_status = "not_found";
  value.candidates[0].overall_coverage = "unmet";
  row.matching_result.matches[0].evidence = [];
  value.ranking[0].ambiguous_count = 0; value.ranking[0].not_found_count = 1;
  assert.ok(isBatchScreeningResponse(value));
  html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
  assert.ok(html.includes("1 not found"));
});

test("runtime validation rejects falsified ranks/counts, missing rankings and noneligible members", () => {
  for (const mutate of [
    (r: BatchScreeningResponse) => {r.ranking[0].supported_count = 0;},
    (r: BatchScreeningResponse) => {r.ranking[0].rank = 2;},
    (r: BatchScreeningResponse) => {r.ranking[0].rank = 1.5;},
    (r: BatchScreeningResponse) => {r.ranking[0].tied = true;},
    (r: BatchScreeningResponse) => {r.ranking[0].upload_id = batchId;},
    (r: BatchScreeningResponse) => {r.ranking = [];},
    (r: BatchScreeningResponse) => {r.candidates[0].result = null; r.candidates[0].error_code = "screening_processing_failed";},
  ]) {const value = result(); mutate(value); assert.ok(!isBatchScreeningResponse(value));}
});

test("higher supported counts precede lower counts and do not count preferred ambiguity", () => {
  const value = result(), other = structuredClone(value.candidates[0]);
  value.snapshot.criteria[0].is_hard = false;
  value.candidates[0].result!.matching_result.requirement_context.hard_requirement_ids = [];
  other.upload_id = batchId; other.result!.upload_id = batchId; other.result!.matching_result.upload_id = batchId;
  other.result!.matching_result.requirement_context.hard_requirement_ids = [];
  other.result!.matching_result.matches[0].match_status = "ambiguous";
  other.overall_coverage = "uncertain";
  value.candidates.push(other); value.processed_count = 2;
  value.ranking.push({upload_id: batchId, rank: 2, tied: false, supported_count: 0, ambiguous_count: 1, not_found_count: 0, total_requirements: 1});
  assert.ok(isBatchScreeningResponse(value));
  const html = renderToStaticMarkup(createElement(ScreeningResults, {result: value}));
  assert.ok(html.indexOf("Upload 1") < html.indexOf("Upload 2"));
  assert.ok(html.includes("Rank 2") && html.includes("1 ambiguous"));
});
