import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { uploadCvs, validateCvSelection } from "../api/cvUploads";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";
import { extractCvs } from "../api/cvExtraction";
import { runCvOcr } from "../api/cvOcr";
import type { CvOcrResponse } from "../types/cvOcr";
import { CvExtractionSummary, CvOcrSummary, CvUploadConfirmation, SelectedCvFiles, ScreeningWorkflowSteps, screeningPrerequisiteMessage } from "./cvIntakePresentation";
import { extractCandidateProfiles } from "../api/candidateProfiles";
import type { CandidateProfilesResponse } from "../types/candidateProfile";
import { CandidateProfileAction, CandidateProfilesSummary } from "./candidateProfilesPresentation";
import ScreeningCriteriaReview from "./ScreeningCriteriaReview";
import { ScreeningResults } from "./screeningPresentation";
import { screenCvBatch } from "../api/screening";
import type { BatchScreeningResponse, ReviewedJobSnapshot, ScreeningSuggestions } from "../types/screening";

export default function CvIntake({suggestions = null}: {suggestions?: ScreeningSuggestions | null}) {
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
  const screeningRevision = useRef(0);
  const busy = loading || extracting || processingOcr || parsing || screeningBusy;
  const screeningPrerequisite = screeningPrerequisiteMessage({busy, hasSuggestions: Boolean(suggestions), hasBatch: Boolean(result),
    hasSnapshot: Boolean(snapshot), referenceMatches: Boolean(result && snapshot && snapshot.job_reference === result.job_reference)});
  function invalidateCriteria() { screeningRevision.current++; setSnapshot(null); setScreening(null); }
  useEffect(() => { invalidateCriteria(); }, [suggestions]);
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
      <div className="page-intro"><p className="eyebrow">Recruiter workspace</p><h1>CV intake and screening</h1><p className="page-description">Review the job requirements, add a CV batch and inspect evidence-backed screening results.</p></div>
      <ScreeningWorkflowSteps hasSuggestions={Boolean(suggestions)} hasSnapshot={Boolean(snapshot)} hasBatch={Boolean(result)} isScreened={Boolean(screening)} />
      <section className="card cv-intake-card" aria-label="Native CV upload">
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <legend className="sr-only">CV intake details</legend>
            <div className="field"><label htmlFor="cv-job-reference">Job Reference</label>
              <input id="cv-job-reference" value={reference} maxLength={23} required placeholder="TT-JOB-XXXXXXXXXXXXXXXX" onChange={event => {setReference(event.target.value); invalidateCriteria(); setError(""); setResult(null); setExtraction(null); setOcr(null); clearProfiles();}} />
              <p className="helper-text">Copy the reference from the published job. Demo association only; no persisted job profile.</p>
            </div>
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
        {suggestions ? <ScreeningCriteriaReview key={JSON.stringify(suggestions) + reference} suggestions={suggestions} jobReference={reference} disabled={busy}
          onInvalidate={invalidateCriteria} onConfirm={value => {setSnapshot(value); setScreening(null); setError("");}} />
          : <p className="helper-text">Generate a JD in the assistant and choose Review screening criteria to begin.</p>}
        {snapshot && <p role="status" className="session-confirmation">Criteria confirmed for <strong>{snapshot.job_reference}</strong><span> Session only; not saved as a job profile.</span></p>}
        <div className="screening-action">
          <div><h2>Screen this CV batch</h2><p className="helper-text">Uses the stored files and confirmed criteria. Parsing runs as part of screening.</p></div>
          <button type="button" className="button button-primary" disabled={Boolean(screeningPrerequisite)} onClick={() => void screen()}>{screeningBusy ? "Screening CV batch…" : "Screen CV batch"}</button>
        </div>
        {screeningPrerequisite && <p className="prerequisite-hint" role="status">{screeningPrerequisite}</p>}
        {screening && <ScreeningResults result={screening} />}
      </section>
    </main>
  </div>;
}
