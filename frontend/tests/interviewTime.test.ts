import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { localSchedule, timezoneOptions } from "../src/components/interviewTime.ts";
import { ScheduleForm } from "../src/components/InterviewScheduling.ts";
import { createInterview } from "../src/api/interviews.ts";
import type { CandidateScore } from "../src/types/screening.ts";

test("chosen timezone converts independently of browser zone, including date rollover and fractional offsets", () => {
  for (const [local, zone, utc] of [
    ["2027-01-20T15:00", "Asia/Dhaka", "2027-01-20T09:00:00.000Z"],
    ["2027-01-20T01:00", "Asia/Dhaka", "2027-01-19T19:00:00.000Z"],
    ["2027-01-20T15:00", "Asia/Kathmandu", "2027-01-20T09:15:00.000Z"],
    ["2027-01-20T15:00", "America/New_York", "2027-01-20T20:00:00.000Z"],
    ["2027-07-20T15:00", "America/New_York", "2027-07-20T19:00:00.000Z"],
    ["2027-01-20T15:00", "UTC", "2027-01-20T15:00:00.000Z"],
  ]) assert.deepEqual(localSchedule(local, zone, 0), { utc });
});

test("invalid dates, zones, past and exactly-now timestamps cannot be submitted", () => {
  for (const local of ["", "2027-02-30T12:00", "2027-13-01T12:00", "2027-01-01T24:00", "2027-01-01T12:00Z", "2027-01-01T12:00:10"])
    assert.match(localSchedule(local, "UTC", 0).error!, /valid local/);
  assert.match(localSchedule("2027-01-01T12:00", "Not/AZone", 0).error!, /valid IANA/);
  const instant = Date.parse("2027-01-01T06:00:00Z");
  for (const now of [instant, instant + 1])
    assert.match(localSchedule("2027-01-01T12:00", "Asia/Dhaka", now).error!, /future/);
});

test("DST gaps and overlaps are rejected, including thirty-minute transitions", () => {
  for (const [local, zone, message] of [
    ["2027-03-14T02:30", "America/New_York", /does not exist/],
    ["2027-11-07T01:30", "America/New_York", /occurs twice/],
    ["2027-10-03T02:15", "Australia/Lord_Howe", /does not exist/],
    ["2027-04-04T01:45", "Australia/Lord_Howe", /occurs twice/],
    ["2011-12-30T12:00", "Pacific/Apia", /does not exist/],
  ] as const) assert.match(localSchedule(local, zone, 0).error!, message);
  assert.equal(localSchedule("2027-03-14T03:30", "America/New_York", 0).utc, "2027-03-14T07:30:00.000Z");
});

const candidate: CandidateScore = { job_reference: "TT-JOB-1234567812344234", upload_id: "12345678-1234-4234-8234-123456789abc",
  screening_decision: "eligible", status: "not_evaluated", reason: "uncertain_evidence",
  weights: { skill: 50, experience: 30, education: 20 }, score: null, dimensions: [] };

test("local form exposes a selectable timezone, UTC preview and unchanged unscored confirmation", () => {
  let zone = "Asia/Dhaka";
  const props = { candidate, start: "2070-01-20T15:00", zone, duration: 30, confirmed: false, busy: false, alreadyScheduled: false,
    onStart: () => {}, onZone: (value: string) => { zone = value; }, onDuration: () => {}, onConfirmed: () => {}, onSubmit: () => {} };
  const html = renderToStaticMarkup(createElement(ScheduleForm, props));
  for (const text of ["Local interview date and time", "Interview timezone (IANA)", "2070-01-20T09:00:00.000Z", "Eligible but not scored"])
    assert.ok(html.includes(text), text);
  assert.match(html, /<select id="interview-zone"/);
  assert.match(html, /disabled=""[^>]*>Schedule interview/);
  const form = ScheduleForm(props);
  const fields = (form.props.children as React.ReactElement[])[3];
  const select = (fields.props.children as React.ReactElement[]).find(child => child?.type === "select")!;
  select.props.onChange({ target: { value: "America/New_York" } });
  assert.equal(zone, "America/New_York");
  const changed = renderToStaticMarkup(createElement(ScheduleForm, { ...props, zone }));
  assert.ok(changed.includes("2070-01-20T20:00:00.000Z"));
  assert.ok(timezoneOptions("Asia/Dhaka").includes("UTC"));
});

test("DST failure is visible in the form rather than showing an invented UTC preview", () => {
  const html = renderToStaticMarkup(createElement(ScheduleForm, { candidate, start: "2070-11-02T01:30", zone: "America/New_York",
    duration: 30, confirmed: true, busy: false, alreadyScheduled: false,
    onStart: () => {}, onZone: () => {}, onDuration: () => {}, onConfirmed: () => {}, onSubmit: () => {} }));
  assert.ok(html.includes("occurs twice"));
  assert.ok(!html.includes("UTC:"));
});

test("converted UTC uses the unchanged interview API payload and response association", async t => {
  const id = candidate.upload_id;
  const scheduled_at = localSchedule("2070-01-20T15:00", "Asia/Dhaka", 0).utc!;
  const request = { batch_id: id, upload_id: id, criteria_revision: 2, scoring_version: "f2-coverage-v1" as const,
    selection_confirmed: true as const, confirm_eligible_unscored: true, scheduled_at, timezone: "Asia/Dhaka", duration_minutes: 30 };
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.deepEqual(JSON.parse(String(options?.body)), request);
    return Response.json({ id, job_id: id, job_reference: candidate.job_reference, batch_id: id, upload_id: id,
      criteria_revision: 2, scoring_version: "f2-coverage-v1", scheduled_at, timezone: "Asia/Dhaka", duration_minutes: 30,
      unscored_confirmed: true, status: "scheduled" });
  });
  assert.equal((await createInterview(id, request)).scheduled_at, "2070-01-20T09:00:00.000Z");
});
