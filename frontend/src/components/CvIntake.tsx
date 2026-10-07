import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { uploadCvs, validateCvSelection } from "../api/cvUploads";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";
import { extractCvs } from "../api/cvExtraction";
import { runCvOcr } from "../api/cvOcr";
import type { CvOcrResponse } from "../types/cvOcr";
import { CvExtractionSummary, CvOcrSummary, CvUploadConfirmation, SelectedCvFiles } from "./cvIntakePresentation";

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
  const pending = useRef(false);
  const picker = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const invalid = validateCvSelection(reference, files);
    if (invalid) { setError(invalid); return; }
    pending.current = true;
    setLoading(true); setError(""); setResult(null); setExtraction(null); setOcr(null);
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
    try { setExtraction(await extractCvs(result)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Text extraction could not be completed."); }
    finally { pending.current = false; setExtracting(false); }
  }

  async function runOcr() {
    if (!extraction || pending.current) return;
    pending.current = true;
    setProcessingOcr(true); setError(""); setOcr(null);
    try { setOcr(await runCvOcr(extraction)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "OCR could not be completed."); }
    finally { pending.current = false; setProcessingOcr(false); }
  }

  return <div className="app-shell chat-page">
    <header className="site-header"><a className="brand" href="/">TalentTrace AI</a><span className="workspace-label">Recruiter workspace</span></header>
    <main>
      <div className="page-intro"><h1>CV intake</h1><p className="page-description">Upload sample PDF/DOCX files and check digital text extraction. No candidate parsing or screening yet.</p></div>
      <section className="card cv-intake-card" aria-label="Native CV upload">
        <form onSubmit={submit}>
          <fieldset disabled={loading || extracting || processingOcr}>
            <legend className="sr-only">CV intake details</legend>
            <div className="field"><label htmlFor="cv-job-reference">Job Reference</label>
              <input id="cv-job-reference" value={reference} maxLength={23} required placeholder="TT-JOB-XXXXXXXXXXXXXXXX" onChange={event => {setReference(event.target.value); setError(""); setResult(null); setExtraction(null); setOcr(null);}} />
              <p className="helper-text">Copy the reference from the published job. Demo association only; no persisted job profile.</p>
            </div>
            <div className="field"><label htmlFor="cv-files">Choose CV files</label>
              <input ref={picker} id="cv-files" type="file" accept=".pdf,.docx" multiple onChange={event => {
                setFiles(Array.from(event.target.files ?? [])); setError(""); setResult(null); setExtraction(null); setOcr(null);
              }} />
              <p className="helper-text">1–20 files. Up to 10 MiB each and 100 MiB per batch. Use synthetic/sample CVs only.</p>
            </div>
            <SelectedCvFiles files={files} disabled={loading || extracting || processingOcr} onRemove={index => {setFiles(previous => previous.filter((_, i) => i !== index)); setError("");}} />
          </fieldset>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button className="button button-primary" type="submit" disabled={loading || extracting || processingOcr}>{loading ? "Uploading CVs…" : "Upload CVs"}</button>
          {loading && <p role="status">Validating and storing your batch…</p>}
          <p className="form-note">Trusted local demo. No candidate data is sent to the JD Agent, MCP publishing or RAG.</p>
        </form>
        {result && <CvUploadConfirmation result={result} onExtract={processingOcr ? undefined : extract} extracting={extracting} />}
        {extraction && <CvExtractionSummary result={extraction} onOcr={runOcr} processingOcr={processingOcr} disabled={loading || extracting} />}
        {ocr && <CvOcrSummary result={ocr} />}
      </section>
    </main>
  </div>;
}
