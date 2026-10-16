import {useEffect,useRef,useState} from 'react';
import {analysisConfig,startAnalysis,analysisStatus} from '../api/interviewAnalysis';
import type {AnalysisConfig,AnalysisOperation} from '../api/interviewAnalysis';

export default function InterviewAnalysis({jobId,interviewId,revision}:{jobId:string;interviewId:string;revision:number}){
  const [config,setConfig]=useState<AnalysisConfig|null>(null),[checked,setChecked]=useState(false);
  const [operation,setOperation]=useState<AnalysisOperation|null>(null),[id,setId]=useState<string|null>(null);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('No analysis has been requested.');
  const [retryConfirmed,setRetryConfirmed]=useState(false);
  const generation=useRef(0),pending=useRef(false),posting=useRef(false);
  useEffect(()=>{const current=++generation.current;setOperation(null);setId(null);setChecked(false);setConfig(null);setBusy(false);setMessage('No analysis has been requested.');
    void analysisConfig().then(v=>{if(current===generation.current)setConfig(v);}).catch(()=>{if(current===generation.current)setMessage('Analysis service unavailable.');});
    return()=>{generation.current++;};},[jobId,interviewId,revision]);
  async function refresh(){if(!id||pending.current)return;const current=generation.current;pending.current=true;
    try{const v=await analysisStatus(jobId,interviewId,id);if(current===generation.current){setOperation(v);setMessage(v.status==='failed'?'Processing failed; this is not a candidate rejection.':'Status checked.');}}
    catch{if(current===generation.current){setOperation(null);setMessage('Analysis unavailable, expired, withdrawn or lost after restart. Displayed results cleared. No model request repeated.');}}
    finally{pending.current=false;}}
  useEffect(()=>{if(!id)return;const timer=setInterval(()=>void refresh(),2000);return()=>clearInterval(timer);},[id,jobId,interviewId,revision]);
  async function start(){if(busy||id||!checked||posting.current)return;posting.current=true;const current=generation.current;const next=crypto.randomUUID();setId(next);setBusy(true);setOperation(null);
    try{const v=await startAnalysis(jobId,interviewId,revision,next);if(current===generation.current){setId(v.operation_id);setOperation(v);setMessage('Analysis requested. Status checks do not call the model.');}}
    catch{if(current===generation.current)setMessage('Delivery unconfirmed. Use Check analysis status; do not repeat the request.');}
    finally{posting.current=false;if(current===generation.current)setBusy(false);}}
  if(!config?.enabled)return <section className="card" aria-label="Interview analysis"><h2>Interview analysis</h2><p>Synthetic interview analysis is disabled or unavailable. No AI call was made.</p></section>;
  const result=operation?.status==='completed'?operation.result:null;
  return <section className="card" aria-label="Interview analysis"><h2>Post-interview analysis</h2>
    <p>{config.disclosure}</p><p>Requires finalized saved captures and the current confirmed criteria. Accepted audio is not proof of a complete interview. {config.persistence==='postgresql_privacy_bound'?'Results are saved under the transcript withdrawal and retention rules. Restart does not repeat inference; interrupted work needs an explicit retry.':'Results expire from this worker after ten minutes or a restart.'}</p>
    <label><input type="checkbox" checked={checked} disabled={!!id} onChange={e=>setChecked(e.target.checked)}/> I authorize this synthetic-only Groq analysis under the displayed disclosure.</label>
    <div className="button-row"><button disabled={!checked||busy||!!id} onClick={()=>void start()}>Analyze finalized interview</button>
      <button disabled={!id||busy} onClick={()=>void refresh()}>Check analysis status</button></div>
    <p role="status">{message} {operation && `Operation: ${operation.status}`}</p>
    {operation?.error&&<p>{operation.error} — no eligibility decision was made.</p>}
    {operation?.status==='failed'&&operation.persistence==='postgresql_privacy_bound'&&operation.attempt&&<div>
      <label><input type="checkbox" checked={retryConfirmed} onChange={e=>setRetryConfirmed(e.target.checked)}/> I explicitly request a new attempt; this may call the model again.</label>
      <button disabled={!retryConfirmed||busy} onClick={()=>{if(!id||posting.current)return;const current=generation.current;posting.current=true;setBusy(true);setRetryConfirmed(false);
        void startAnalysis(jobId,interviewId,revision,id,operation.attempt).then(v=>{if(current===generation.current)setOperation(v);})
          .catch(()=>{if(current===generation.current)setMessage('Retry unconfirmed. Check the same operation; no automatic repeat.');})
          .finally(()=>{posting.current=false;if(current===generation.current)setBusy(false);});}}>Retry failed analysis once</button></div>}
    {result&&<div><p><strong>{result.outcome==='needs_review'?'Needs human review — technical assessment incomplete.':'AI interpretation — recruiter review required.'}</strong> {result.inference_performed===false?'Deterministic evidence review; no model inference performed.':`${result.provider} / ${result.model}`} · {result.rubric_version}</p>
      <p>{result.warning}</p><p>No overall score or hire/reject recommendation. ASR remains unverified.</p>
      {result.pairs.map(pair=>{const a=result.assessment.answers.find(v=>v.qa_id===pair.id);return <article key={pair.id} className="card">
        <h3>Recruiter question</h3><p>{pair.question}</p><p>Candidate statement: {pair.answer||'No associated answer; not evidence of an incorrect response.'}</p>
        <p>Pairing: {pair.status} · {(pair.start_ms/1000).toFixed(1)}–{(pair.end_ms/1000).toFixed(1)}s within capture</p>
        {pair.warnings.map(w=><p key={w}>Review: {w}</p>)}
        {a?.dimensions.map(d=><div key={d.dimension}><strong>{d.dimension.replaceAll('_',' ')}: {d.status.replaceAll('_',' ')}</strong><p>AI interpretation: {d.justification}</p>
          {d.evidence.map((q,i)=><blockquote key={i}>Transcript evidence: “{q.quote}” <small>turn {q.turn_id}</small></blockquote>)}</div>)}
        {a?.technical_citations.map((r,i)=><p key={i}>Technical reference {r.reference_id}: “{r.quote}”</p>)}
        <p>Suggested follow-up: {a?.follow_up}</p></article>;})}
      <h3>Confirmed requirement coverage</h3>{result.requirements.map(r=><div key={r.criterion_id}><strong>{r.description}: {r.coverage.replaceAll('_',' ')}</strong><p>{r.explanation}</p>
        {result.assessment.answers.filter(a=>r.qa_ids.includes(a.qa_id)).map(a=><div key={a.qa_id}><p>Linked answer assessment — no requirement-level pass/fail inferred.</p>
          {a.dimensions.map(d=><p key={d.dimension}>{d.dimension}: {d.status} — {d.justification}</p>)}</div>)}
        {!r.qa_ids.length&&<p>No associated answer assessment; this is an evidence gap, not lack of skill.</p>}<p>{r.follow_up}</p></div>)}
      <h3>Evidence-linked strengths</h3>{result.strengths.length?result.strengths.map((s,i)=><p key={i}>{s.dimension}: {s.interpretation} (Q&A {s.qa_id})</p>):<p>No supported strengths established.</p>}
      <h3>Gaps and uncertainty</h3>{result.gaps.map(g=><p key={g.criterion_id}>{g.criterion_id}: {g.coverage} — {g.follow_up}</p>)}
      {!!result.unpaired_turn_ids.length&&<p>{result.unpaired_turn_ids.length} source turns were not confidently paired; review the source transcript.</p>}
      <details><summary>Original transcript evidence and speaker labels</summary><ol>{result.turns.map(t=><li key={t.id}>{t.role}: {t.text} · turn {t.id}</li>)}</ol></details>
      <details><summary>Technical knowledge used</summary><p>Small versioned reference corpus; coverage is limited. Summaries and model interpretations are separate.</p>{result.technical_references.map(r=><p key={r.id}>{r.source_title||r.id} ({r.provenance}, {r.version}) · {r.location} · {r.url}: {r.text}</p>)}</details>
    </div>}
  </section>;
}
