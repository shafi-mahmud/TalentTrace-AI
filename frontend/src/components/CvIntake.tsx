import ProviderSelection from "./ProviderSelection";
import {cvProviderReady} from "../api/cvProvider.ts";
import ImportedBatches from './ImportedBatches.ts';
import SavedScores from './SavedScores';
import type { InterviewSelection } from './SavedScores';
import { useLayoutEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { uploadCvs, validateCvSelection } from "../api/cvUploads";
import type { CvUploadResponse } from "../types/cvUpload";
import type { CvExtractionResponse } from "../types/cvExtraction";
import { extractCvs } from "../api/cvExtraction";
import { runCvOcr } from "../api/cvOcr";
import type { CvOcrResponse } from "../types/cvOcr";
import { CvExtractionSummary, CvOcrSummary, CvUploadConfirmation, SelectedCvFiles, ScreeningWorkflowSteps, screeningPrerequisiteMessage, resetCriteriaContextForNewChat } from "./cvIntakePresentation";
import { extractCandidateProfiles } from "../api/candidateProfiles";
import type { CandidateProfilesResponse } from "../types/candidateProfile";
import { CandidateProfileAction, CandidateProfilesSummary } from "./candidateProfilesPresentation";
import ScreeningCriteriaReview from "./ScreeningCriteriaReview";
import { ScreeningResults } from "./screeningPresentation";
import { screenCvBatch } from "../api/screening";
import type { BatchScreeningResponse, ReviewedJobSnapshot } from "../types/screening";
import type { WorkingCriteriaDraft } from "../types/recruiterChat";
import { criteriaSaveStatus } from "../state/recruiterWorkspace";
import { createJob, saveCriteria } from "../api/jobs";
import type { SavedJob } from "../api/jobs";
import { isScoringWeights, loadScores } from "../api/scoring";
import type { ScoringWeights } from "../types/screening";
import { ScoringWeightsEditor } from "./ScoringWeightsEditor";

export default function CvIntake({draft, contextResetKey, onCriteriaChange, onCriteriaReviewed, onJobSaved,onGoToScheduling}: {
  onGoToScheduling:(selection?:InterviewSelection)=>void;
  onJobSaved: (job: SavedJob) => void;
  contextResetKey: number;
  draft: WorkingCriteriaDraft | null; onCriteriaChange: (criteria: WorkingCriteriaDraft["criteria"]) => void;
  onCriteriaReviewed: (reviewed: boolean) => void;
}) {
  const [aiProvider,setAiProvider]=useState("");
  const [externalConfirmed,setExternalConfirmed]=useState(false);
  const selection={provider:aiProvider,externalConfirmed};
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
  const [weights, setWeights] = useState<ScoringWeights>({skill: 50, experience: 30, education: 20});
  useLayoutEffect(() => {setWeights(criteriaDraft?.weights ?? {skill: 50, experience: 30, education: 20});}, [criteriaDraft?.draftId, criteriaDraft?.revision, contextResetKey]);
  useLayoutEffect(()=>{setExternalConfirmed(false);},[criteriaDraft?.draftId,criteriaDraft?.revision,result?.batch_id,contextResetKey]);
  const busy = loading || extracting || processingOcr || parsing || screeningBusy;
  const screeningPrerequisite = screeningPrerequisiteMessage({busy, hasSuggestions: Boolean(criteriaDraft), hasBatch: Boolean(result),
    hasSnapshot: Boolean(snapshot), referenceMatches: Boolean(result && snapshot && snapshot.job_reference === result.job_reference)});
  function invalidateCriteria() { screeningRevision.current++; setSnapshot(null); setScreening(null); }
  useLayoutEffect(() => { invalidateCriteria(); }, [criteriaDraft?.draftId, criteriaDraft?.criteria, criteriaDraft?.reviewed]);
  useLayoutEffect(() => {
    if (criteriaDraft?.jobReference) setReference(criteriaDraft.jobReference);
    if (criteriaDraft?.reviewed && criteriaDraft.savedSnapshot) setSnapshot(criteriaDraft.savedSnapshot);
  }, [criteriaDraft?.draftId, criteriaDraft?.jobReference, criteriaDraft?.criteria, criteriaDraft?.reviewed, criteriaDraft?.savedSnapshot]);
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
  async function createManualDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const revision = screeningRevision.current;
    setLoading(true);
    try {const job = await createJob(manualJobTitle);
      if (revision !== screeningRevision.current) return;
      setReference(job.job_reference); onJobSaved(job);
      setSetupError(""); setError(""); invalidateCriteria();}
    catch {if (revision === screeningRevision.current) setSetupError("Job could not be saved. Check the title and service readiness.");}
    finally {setLoading(false);}
  }
  async function persistCriteria(value: ReviewedJobSnapshot) {
    if (!isScoringWeights(weights)) {setError("Scoring weights must be whole percentages totaling 100."); return;}
    if (!criteriaDraft?.revision) {setError("Reload the saved job before confirming requirements."); return;}
    const revision = screeningRevision.current;
    setLoading(true); setError("");
    try {const job = await saveCriteria(criteriaDraft.draftId, criteriaDraft.revision, value.criteria, true, weights);
      if (revision === screeningRevision.current) {onJobSaved(job); setSnapshot(job.snapshot); setScreening(null);}}
    catch (failure) {setError(failure instanceof Error ? failure.message : "Requirements could not be confirmed.");}
    finally {setLoading(false);}
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
    if (!result || pending.current || !cvProviderReady(selection)) return;
    pending.current = true; setParsing(true); setProfiles(null); setError("");
    try { setProfiles(await extractCandidateProfiles(result,selection)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Candidate profile extraction could not be completed."); }
    finally { pending.current = false; setParsing(false); }
  }

  async function screen() {
    if (!result || !snapshot || pending.current || !cvProviderReady(selection)) return;
    pending.current = true; setScreeningBusy(true); setScreening(null); setError("");
    const revision = screeningRevision.current;
    try {
      const response = await screenCvBatch(result, snapshot, criteriaDraft?.revision,selection);
      if (response.scoring && (response.scoring.job_id !== criteriaDraft?.draftId || response.scoring.criteria_revision !== criteriaDraft?.revision)) throw new Error("Job changed. Reload and review criteria and weights.");
      // Switching to another JD while this request runs invalidates its presentation.
      if (revision === screeningRevision.current) setScreening(response);
    }
    catch (failure) { if (revision === screeningRevision.current) setError(failure instanceof Error ? failure.message : "Batch screening could not be completed."); }
    finally { pending.current = false; setScreeningBusy(false); }
  }

  async function reloadScores() {
    if (!screening || !criteriaDraft?.revision || busy) return;
    const revision = screeningRevision.current;
    setScreeningBusy(true); setError("");
    try {
      const scoring = await loadScores(criteriaDraft.draftId, criteriaDraft.revision, screening);
      if (revision === screeningRevision.current) setScreening({...screening, scoring});
    } catch (failure) {if (revision === screeningRevision.current) setError(failure instanceof Error ? failure.message : "Saved scores could not be loaded.");}
    finally {setScreeningBusy(false);}
  }

  return <div className="app-shell chat-page recruiter-page screening-page">
    <main>
      <div className="page-intro"><p className="eyebrow">Recruiter workspace</p><h1>Review Applicants</h1><p className="page-description">Confirm criteria, choose CVs, then review screening evidence before selecting candidates.</p></div>
      <button className="button button-secondary" onClick={() => onGoToScheduling()}>Schedule Interview</button>
      <ScreeningWorkflowSteps hasSuggestions={Boolean(criteriaDraft)} hasSnapshot={Boolean(snapshot)} hasBatch={Boolean(result)} isScreened={Boolean(screening)} />
      <section className="screening-setup" aria-label="Candidate screening workspace">
        <details className="supporting-details job-reference-details" open={!criteriaDraft?.jobReference}><summary>Job reference</summary><div className="field"><label htmlFor="cv-job-reference">Job Reference</label>
          <input id="cv-job-reference" value={reference} readOnly={Boolean(criteriaDraft?.jobReference)} maxLength={23} required placeholder="Create or select a job first" onChange={event => {
            setReference(event.target.value); invalidateCriteria(); changeReviewed(false); setError(""); setSetupError("");
          }} />
          <p className="helper-text">This reference belongs to the active saved job. Requirements must be confirmed before screening.</p>
        </div>
        </details>
        {criteriaDraft?.jobReference && !criteriaDraft.reviewed && <p role="status" className="helper-text">{criteriaSaveStatus(criteriaDraft)}</p>}
        <details className="stage-disclosure criteria-stage" open={!criteriaDraft?.reviewed}><summary>{criteriaDraft?.reviewed ? `Requirements confirmed · ${criteriaDraft.criteria.length} ${criteriaDraft.criteria.length === 1 ? "requirement" : "requirements"} · review or edit` : "Job requirements · review and confirm"}</summary>
        {criteriaDraft && <ScoringWeightsEditor weights={weights} disabled={busy} reviewed={criteriaDraft.reviewed}
          onChange={value => {setWeights(value); invalidateCriteria(); changeReviewed(false);}} />}
        {criteriaDraft ? <ScreeningCriteriaReview suggestions={criteriaDraft.suggestions} criteria={criteriaDraft.criteria} sources={criteriaDraft.sources}
          reviewed={criteriaDraft.reviewed} jobReference={reference} disabled={busy} origin={criteriaDraft.origin}
          onChange={changeCriteria} onReviewedChange={changeReviewed}
          onConfirm={value => {void persistCriteria(value);}} /> :
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
        </details>
        <ProviderSelection scope="cv" value={aiProvider} consent={externalConfirmed} disabled={busy} onChange={v=>{setAiProvider(v);setExternalConfirmed(false);}} onConsent={setExternalConfirmed}/>
        {criteriaDraft?.revision && criteriaDraft.jobReference && <ImportedBatches key={criteriaDraft.draftId+':'+criteriaDraft.revision} jobId={criteriaDraft.draftId} reference={criteriaDraft.jobReference} revision={criteriaDraft.revision} snapshot={snapshot} disabled={busy} selection={selection} onBusy={setScreeningBusy} onResult={setScreening} onContextChange={()=>setExternalConfirmed(false)} />}
        <section className="card cv-intake-card" aria-label="Candidate CV upload">
          {error && <div className="error-banner" role="alert">{error}</div>}
          <details className="stage-disclosure upload-stage" open={!result}><summary>{result ? `${result.accepted_count} CVs uploaded · choose another batch` : "Upload candidate CVs"}</summary>
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
          <button className="button button-primary" type="submit" disabled={busy}>{loading ? "Uploading CVs…" : "Upload CVs"}</button>
          {loading && <p role="status">Validating and storing your batch…</p>}
          <p className="form-note">Synthetic/sample CVs only. AI processing uses the selected CV provider.</p>
          <details className="supporting-details"><summary>How screening works</summary><p>Files are stored privately. CV data is not sent to JD, RAG or MCP. Review extracted evidence before making hiring decisions.</p></details>
        </form>
        </details>
        {result && <details className="supporting-details"><summary>Document preparation and OCR preview</summary><CvUploadConfirmation result={result} onExtract={processingOcr || parsing || screeningBusy ? undefined : extract} extracting={extracting} />
        {extraction && <CvExtractionSummary result={extraction} onOcr={runOcr} processingOcr={processingOcr} disabled={busy} />}
        {ocr && <CvOcrSummary result={ocr} />}
        <CandidateProfileAction extraction={extraction} ocrAttempted={ocrAttempted} busy={busy||!cvProviderReady(selection)} parsing={parsing} onParse={parseProfiles} />
        {profiles && <CandidateProfilesSummary result={profiles} />}
        </details>}
        <div className="screening-action">
          <div><h2>Run AI Screening</h2><p className="helper-text">Uses confirmed criteria and prepares documents, including OCR where needed.</p></div>
          <button type="button" className="button button-primary" disabled={Boolean(screeningPrerequisite)||!cvProviderReady(selection)} onClick={() => void screen()}>{screeningBusy ? "Screening applicants…" : "Run AI Screening"}</button>
        </div>
        {screeningPrerequisite && <p className="prerequisite-hint" role="status">{screeningPrerequisite}</p>}
        {screening && <><details className="supporting-details"><summary>Batch details</summary><p>{screening.batch_id}</p></details><button className="button button-secondary" disabled={busy} onClick={() => void reloadScores()}>Reload saved scores</button><ScreeningResults result={screening} onSelectCandidate={uploadId => {const batch=screening.scoring; const candidate=batch?.candidates.find(c=>c.upload_id===uploadId); if(batch && candidate) onGoToScheduling({batch,candidate});}} /></>}
        {criteriaDraft?.revision && <SavedScores key={criteriaDraft.draftId} jobId={criteriaDraft.draftId} revision={criteriaDraft.revision} onSelectCandidate={onGoToScheduling} />}
        </section>
      </section>
    </main>
  </div>;
}
