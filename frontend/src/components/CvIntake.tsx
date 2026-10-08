import { useLayoutEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { uploadCvs, validateCvSelection } from "../api/cvUploads";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";
import { extractCvs } from "../api/cvExtraction";
import { runCvOcr } from "../api/cvOcr";
import type { CvOcrResponse } from "../types/cvOcr";
import { createManualCriteriaDraft, CvExtractionSummary, CvOcrSummary, CvUploadConfirmation, SelectedCvFiles, ScreeningWorkflowSteps, screeningPrerequisiteMessage, resetCriteriaContextForNewChat } from "./cvIntakePresentation";
import { extractCandidateProfiles } from "../api/candidateProfiles";
import type { CandidateProfilesResponse } from "../types/candidateProfile";
import { CandidateProfileAction, CandidateProfilesSummary } from "./candidateProfilesPresentation";
import ScreeningCriteriaReview from "./ScreeningCriteriaReview";
import { ScreeningResults } from "./screeningPresentation";
import { screenCvBatch } from "../api/screening";
import type { BatchScreeningResponse, ReviewedJobSnapshot } from "../types/screening";
import type { WorkingCriteriaDraft } from "../types/recruiterChat";

export default function CvIntake({draft, contextResetKey, onCriteriaChange, onCriteriaReviewed}: {
  contextResetKey: number;
  draft: WorkingCriteriaDraft | null; onCriteriaChange: (criteria: WorkingCriteriaDraft["criteria"]) => void;
  onCriteriaReviewed: (reviewed: boolean) => void;
}) {
  const [reference, setReference] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CvUploadResponse | null>(null);
  const [extraction, setExtraction] = useState<CvExtractionResponse | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [ocr, setOcr] = useState<CvOcrResponse | null>(null);
  const [processingOcr, setProcessingOcr] = useState(false);
  const [ocrAttempted, setOcrAttempted] = useState(false);
  const [profiles, setProfiles] = useState<CandidateProfilesResponse | null>(null);
  const [parsing, setParsing] = useState(false);
  const [snapshot, setSnapshot] = useState<ReviewedJobSnapshot | null>(null);
  const [screening, setScreening] = useState<BatchScreeningResponse | null>(null);
  const [screeningBusy, setScreeningBusy] = useState(false);
  const [manualDraft, setManualDraft] = useState<WorkingCriteriaDraft | null>(null);
  const [manualJobTitle, setManualJobTitle] = useState("");
  const [setupError, setSetupError] = useState("");
  const screeningRevision = useRef(0);
  const previousContextResetKey = useRef(contextResetKey);
  const criteriaDraft = draft ?? manualDraft;
  const busy = loading || extracting || processingOcr || parsing || screeningBusy;
  const screeningPrerequisite = screeningPrerequisiteMessage({busy, hasSuggestions: Boolean(criteriaDraft), hasBatch: Boolean(result),
    hasSnapshot: Boolean(snapshot), referenceMatches: Boolean(result && snapshot && snapshot.job_reference === result.job_reference)});
  function invalidateCriteria() { screeningRevision.current++; setSnapshot(null); setScreening(null); }
  useLayoutEffect(() => { invalidateCriteria(); }, [criteriaDraft?.draftId, criteriaDraft?.criteria, criteriaDraft?.reviewed]);
  useLayoutEffect(() => {
    if (previousContextResetKey.current === contextResetKey) return;
    previousContextResetKey.current = contextResetKey;
    const next = resetCriteriaContextForNewChat({reference, manualDraft, manualJobTitle, setupError, snapshot, screening});
    setReference(next.reference); setManualDraft(next.manualDraft); setManualJobTitle(next.manualJobTitle);
    setSetupError(next.setupError); setSnapshot(next.snapshot); setScreening(next.screening); setError("");
    screeningRevision.current++;
  }, [contextResetKey]);
  function changeCriteria(criteria: WorkingCriteriaDraft["criteria"]) {
    if (draft) onCriteriaChange(criteria);
    else setManualDraft(current => current ? {...current, criteria, reviewed: false} : current);
  }
  function changeReviewed(reviewed: boolean) {
    if (draft) onCriteriaReviewed(reviewed);
    else setManualDraft(current => current ? {...current, reviewed} : current);
  }
  function createManualDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = createManualCriteriaDraft(manualJobTitle, reference);
    if (!created) { setSetupError("Enter a job title and a valid TT-JOB reference before adding criteria."); return; }
    setManualDraft(created); setSetupError(""); setError(""); invalidateCriteria();
  }
  function clearProfiles() { setProfiles(null); setOcrAttempted(false); }
  const pending = useRef(false);
  const picker = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const invalid = validateCvSelection(reference, files);
    if (invalid) { setError(invalid); return; }
    pending.current = true;
    setLoading(true); setError(""); setResult(null); setExtraction(null); setOcr(null);
    clearProfiles(); setScreening(null);
    try {
      setResult(await uploadCvs(reference, files));
      setFiles([]);
      if (picker.current) picker.current.value = "";
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Upload could not be confirmed.");
    } finally {
      pending.current = false;
      setLoading(false);
    }
  }

  async function extract() {
    if (!result || pending.current) return;
    pending.current = true;
    setExtracting(true); setError(""); setExtraction(null); setOcr(null);
    clearProfiles();
    try { setExtraction(await extractCvs(result)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Text extraction could not be completed."); }
    finally { pending.current = false; setExtracting(false); }
  }

  async function runOcr() {
    if (!extraction || pending.current) return;
    pending.current = true;
    setProcessingOcr(true); setError(""); setOcr(null);
    setProfiles(null);
    try { setOcr(await runCvOcr(extraction)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "OCR could not be completed."); }
    finally { pending.current = false; setProcessingOcr(false); setOcrAttempted(true); }
  }

  async function parseProfiles() {
    if (!result || pending.current) return;
    pending.current = true; setParsing(true); setProfiles(null); setError("");
    try { setProfiles(await extractCandidateProfiles(result)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Candidate profile extraction could not be completed."); }
    finally { pending.current = false; setParsing(false); }
  }

  async function screen() {
    if (!result || !snapshot || pending.current) return;
    pending.current = true; setScreeningBusy(true); setScreening(null); setError("");
    const revision = screeningRevision.current;
    try {
      const response = await screenCvBatch(result, snapshot);
      // Switching to another JD while this request runs invalidates its presentation.
      if (revision === screeningRevision.current) setScreening(response);
    }
    catch (failure) { if (revision === screeningRevision.current) setError(failure instanceof Error ? failure.message : "Batch screening could not be completed."); }
    finally { pending.current = false; setScreeningBusy(false); }
  }

  return <div className="app-shell chat-page">
    <main>
      <div className="page-intro"><p className="eyebrow">Recruiter workspace</p><h1>Candidate Screening Workspace</h1><p className="page-description">Set up job criteria and a CV batch in either order, then review evidence-backed screening results.</p></div>
      <ScreeningWorkflowSteps hasSuggestions={Boolean(criteriaDraft)} hasSnapshot={Boolean(snapshot)} hasBatch={Boolean(result)} isScreened={Boolean(screening)} />
      <section className="card cv-intake-card" aria-label="Candidate screening workspace">
        <div className="field"><label htmlFor="cv-job-reference">Job Reference</label>
          <input id="cv-job-reference" value={reference} maxLength={23} required placeholder="TT-JOB-XXXXXXXXXXXXXXXX" onChange={event => {
            setReference(event.target.value); invalidateCriteria(); changeReviewed(false); setError(""); setSetupError("");
          }} />
          <p className="helper-text">Use the reference for this demo job. The reviewed criteria snapshot is session-only; no saved job profile is created.</p>
        </div>
        {criteriaDraft ? <ScreeningCriteriaReview suggestions={criteriaDraft.suggestions} criteria={criteriaDraft.criteria} sources={criteriaDraft.sources}
          reviewed={criteriaDraft.reviewed} jobReference={reference} disabled={busy} origin={criteriaDraft.origin}
          onChange={changeCriteria} onReviewedChange={changeReviewed}
          onConfirm={value => {setSnapshot(value); setScreening(null); setError("");}} /> :
          <section className="card criteria-review-card" aria-label="Set up screening criteria">
            <h2>Set up screening criteria</h2>
            <p className="helper-text">A generated JD is optional. Add the job title and enter the requirements you want to evaluate.</p>
            <form onSubmit={createManualDraft}>
              <div className="field"><label htmlFor="screening-job-title">Job title</label>
                <input id="screening-job-title" value={manualJobTitle} maxLength={120} required onChange={event => setManualJobTitle(event.target.value)} />
              </div>
              {setupError && <p className="error-banner" role="alert">{setupError}</p>}
              <button className="button button-primary" type="submit" disabled={busy}>Add screening criteria</button>
            </form>
          </section>}
        {snapshot && <p role="status" className="session-confirmation">Criteria confirmed for <strong>{snapshot.job_reference}</strong><span> Session only; not saved as a job profile.</span></p>}
        <section className="card cv-intake-card" aria-label="Candidate CV upload">
          <h2>Upload candidate CVs</h2>
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <legend className="sr-only">Candidate CV upload</legend>
            <div className="field"><label htmlFor="cv-files">Choose CV files</label>
              <input ref={picker} id="cv-files" type="file" accept=".pdf,.docx" multiple onChange={event => {
                setFiles(Array.from(event.target.files ?? [])); setScreening(null); setError(""); setResult(null); setExtraction(null); setOcr(null);
                clearProfiles();
              }} />
              <p className="helper-text">1–20 files. Up to 10 MiB each and 100 MiB per batch. Use synthetic/sample CVs only.</p>
            </div>
            <SelectedCvFiles files={files} disabled={busy} onRemove={index => {setFiles(previous => previous.filter((_, i) => i !== index)); setError("");}} />
          </fieldset>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button className="button button-primary" type="submit" disabled={busy}>{loading ? "Uploading CVs…" : "Upload CVs"}</button>
          {loading && <p role="status">Validating and storing your batch…</p>}
          <p className="form-note">Trusted local demo. Profile extraction sends CV-derived text to Groq. Synthetic/sample CVs only. CV data is not sent to JD, RAG or MCP.</p>
        </form>
        {result && <CvUploadConfirmation result={result} onExtract={processingOcr || parsing || screeningBusy ? undefined : extract} extracting={extracting} />}
        {extraction && <CvExtractionSummary result={extraction} onOcr={runOcr} processingOcr={processingOcr} disabled={busy} />}
        {ocr && <CvOcrSummary result={ocr} />}
        <CandidateProfileAction extraction={extraction} ocrAttempted={ocrAttempted} busy={busy} parsing={parsing} onParse={parseProfiles} />
        {profiles && <CandidateProfilesSummary result={profiles} />}
        <div className="screening-action">
          <div><h2>Screen this CV batch</h2><p className="helper-text">Uses the stored files and confirmed criteria. Parsing runs as part of screening.</p></div>
          <button type="button" className="button button-primary" disabled={Boolean(screeningPrerequisite)} onClick={() => void screen()}>{screeningBusy ? "Screening CV batch…" : "Screen CV batch"}</button>
        </div>
        {screeningPrerequisite && <p className="prerequisite-hint" role="status">{screeningPrerequisite}</p>}
        {screening && <ScreeningResults result={screening} />}
        </section>
      </section>
    </main>
  </div>;
}
