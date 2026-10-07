import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { uploadCvs, validateCvSelection } from "../api/cvUploads";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";
import { extractCvs } from "../api/cvExtraction";
import { runCvOcr } from "../api/cvOcr";
import type { CvOcrResponse } from "../types/cvOcr";
import { CvExtractionSummary, CvOcrSummary, CvUploadConfirmation, SelectedCvFiles } from "./cvIntakePresentation";
import { extractCandidateProfiles } from "../api/candidateProfiles";
import type { CandidateProfilesResponse } from "../types/candidateProfile";
import { CandidateProfileAction, CandidateProfilesSummary } from "./candidateProfilesPresentation";

export default function CvIntake() {
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
  const busy = loading || extracting || processingOcr || parsing;
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
    clearProfiles();
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

  return <div className="app-shell chat-page">
    <header className="site-header"><a className="brand" href="/">TalentTrace AI</a><span className="workspace-label">Recruiter workspace</span></header>
    <main>
      <div className="page-intro"><h1>CV intake</h1><p className="page-description">Extract source-backed candidate profiles from sample CVs. No screening or scoring.</p></div>
      <section className="card cv-intake-card" aria-label="Native CV upload">
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <legend className="sr-only">CV intake details</legend>
            <div className="field"><label htmlFor="cv-job-reference">Job Reference</label>
              <input id="cv-job-reference" value={reference} maxLength={23} required placeholder="TT-JOB-XXXXXXXXXXXXXXXX" onChange={event => {setReference(event.target.value); setError(""); setResult(null); setExtraction(null); setOcr(null); clearProfiles();}} />
              <p className="helper-text">Copy the reference from the published job. Demo association only; no persisted job profile.</p>
            </div>
            <div className="field"><label htmlFor="cv-files">Choose CV files</label>
              <input ref={picker} id="cv-files" type="file" accept=".pdf,.docx" multiple onChange={event => {
                setFiles(Array.from(event.target.files ?? [])); setError(""); setResult(null); setExtraction(null); setOcr(null);
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
        {result && <CvUploadConfirmation result={result} onExtract={processingOcr || parsing ? undefined : extract} extracting={extracting} />}
        {extraction && <CvExtractionSummary result={extraction} onOcr={runOcr} processingOcr={processingOcr} disabled={busy} />}
        {ocr && <CvOcrSummary result={ocr} />}
        <CandidateProfileAction extraction={extraction} ocrAttempted={ocrAttempted} busy={busy} parsing={parsing} onParse={parseProfiles} />
        {profiles && <CandidateProfilesSummary result={profiles} />}
      </section>
    </main>
  </div>;
}
