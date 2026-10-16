import {createElement as h,useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {fetchReport} from '../api/consolidatedAssessment.ts';
import type {ConsolidatedReport,EvidenceState} from '../api/consolidatedAssessment';
import {ScoreDetails} from './scorePresentation.ts';

const messages:Record<EvidenceState,string>={
 available:'Saved interview assessment available.',not_scheduled:'No interview is scheduled for this application.',
 disabled:'Interview evidence access is disabled in this environment.',withdrawn:'Interview evidence withdrawn; no interview text is disclosed.',
 expired:'Interview evidence retention expired; no interview text is disclosed.',deleted:'Interview evidence deleted; no interview text is disclosed.',
 stale:'Interview evidence does not match the current criteria or transcript. Review required.',
 missing_analysis:'No persisted interview analysis is available. This is not a performance assessment.',
 pending:'Interview analysis is pending. Viewing this report does not start or retry it.',
 unavailable:'Interview evidence is unavailable or could not be verified. Missing evidence is not poor performance.',
 ambiguous:'Multiple saved analysis versions exist. Explicit version selection is required.'};

export function AssessmentView({report:r}:{report:ConsolidatedReport}) {
 const instance=useId();
 const prefix=`f6-${instance}-${r.job_id}-${r.batch_id}-${r.upload_id}`;
 const sourceLink=(id:string,text:string)=>h('a',{key:id,href:`#${prefix}-${id}`,onClick:(event:{preventDefault:()=>void})=>{event.preventDefault();const target=document.getElementById(`${prefix}-${id}`);const details=target?.closest('details');if(details)details.open=true;target?.scrollIntoView({block:'center'});}},text);
 const quote=(q:{turn_id:string;quote:string},n:number)=>h('li',{key:n},sourceLink(q.turn_id,`“${q.quote}” — source turn`));
 return h('section',{className:'card','aria-label':'Consolidated candidate assessment'},
  h('h3',null,'Consolidated assessment · F6 Increment 1'),h('p',null,r.job_title),
  h('p',null,`Application ${r.upload_id} · batch ${r.batch_id} · criteria revision ${r.criteria_revision}`),
  h('p',{className:'helper-text'},r.notice),
  h('h4',null,'CV screening and F2'),
  h('p',null,`${r.cv.screening_decision??'No screening decision'} · ${r.cv_source==='interview_selection_snapshot'?'Saved at interview selection; later screening reruns are not substituted.':'Current saved screening result.'}`),
  h(ScoreDetails,{score:r.cv}),
  ...r.cv.dimensions.flatMap(d=>d.matches.map(m=>h('details',{key:m.criterion_id},
   h('summary',null,`${m.criterion_id} · ${m.match_status==='supported'?'CV evidence strength': 'Needs verification'} · ${m.match_status}`),
   h('p',null,m.explanation),...m.evidence.map((e,n)=>h('p',{key:n},`${e.value} — ${e.source.kind} ${e.source.number} (${e.source.method})`))))),
  r.cv.dimensions.length===0&&h('p',null,'No persisted F2 dimension evidence is available; no breakdown is invented.'),
  h('h4',null,'Interview evidence and F5'),h('p',{role:'status'},messages[r.interview.state]),
  r.interview.state==='available'&&h('div',null,
   h('p',null,`Saved operation ${r.interview.operation_id} · rubric ${r.interview.rubric_version}`),
   h('p',null,r.interview.warning),
   h('h4',null,'Requirement coverage and gaps'),
   ...r.interview.requirements.map(m=>h('article',{key:m.criterion_id},h('h5',null,`${m.description} · ${m.coverage}`),
    h('p',null,m.explanation),h('p',null,m.follow_up),...m.turn_ids.map(id=>sourceLink(id,`Source ${id.slice(0,8)} `)))),
   h('h4',null,'Rubric, evidence-linked strengths and verification areas'),
   ...r.interview.assessment!.answers.map(a=>h('article',{key:a.qa_id},
    h('h5',null,r.interview.pairs.find(p=>p.id===a.qa_id)?.question??'Saved question'),
    ...a.dimensions.map(d=>h('div',{key:d.dimension},h('strong',null,`${d.dimension} · ${d.status} · ${d.status==='supported'?'Evidence-linked strength':'Further verification / review'}`),
     h('p',null,d.justification),h('ul',null,...d.evidence.map(quote)))),
    h('p',null,a.follow_up),...a.technical_citations.map((c,n)=>h('p',{key:n},`${c.reference_id}: ${c.quote}`)))),
   h('details',null,h('summary',null,'Saved technical references'),...r.interview.references.map(ref=>h('article',{key:ref.id},h('strong',null,ref.id),h('p',null,ref.text),
    h('p',null,`${ref.provenance} · ${ref.source_title??''} · ${ref.url??''} · ${ref.version??''}`)))),
   h('details',null,h('summary',null,'Authorized timestamped source turns'),...r.interview.turns.map(t=>h('p',{key:t.id,id:`${prefix}-${t.id}`},`${t.role} · capture ${t.session_id} · ${t.start_ms}–${t.end_ms} ms: ${t.text}`)))));
}

export default function ConsolidatedAssessment({jobId,batchId,uploadId}:{jobId:string;batchId:string;uploadId:string}){
 const [report,setReport]=useState<ConsolidatedReport|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const generation=useRef(0),controller=useRef<AbortController|null>(null);
 useLayoutEffect(()=>{generation.current++;controller.current?.abort();setReport(null);setError('');setBusy(false);
  return()=>{generation.current++;controller.current?.abort();};},[jobId,batchId,uploadId]);
 useEffect(()=>{
  const clear=()=>{generation.current++;controller.current?.abort();setReport(null);setBusy(false);};
  const hidden=()=>{if(document.hidden)clear();};
  window.addEventListener('hashchange',clear);document.addEventListener('visibilitychange',hidden);
  const remaining=report?.interview.retention_deadline?Date.parse(report.interview.retention_deadline)-Date.now():null;
  // Retention may exceed the browser's 32-bit timeout limit; recheck at most daily.
  let timer:ReturnType<typeof setTimeout>|undefined;
  function expire(){const left=Date.parse(report!.interview.retention_deadline!)-Date.now();if(left<=0)clear();else timer=setTimeout(expire,Math.min(left,86400000));}
  if(remaining!==null)expire();
  return()=>{window.removeEventListener('hashchange',clear);document.removeEventListener('visibilitychange',hidden);if(timer!==undefined)clearTimeout(timer);};
 },[report]);
 async function load(){
  if(controller.current&&!controller.current.signal.aborted&&busy)return;
  controller.current?.abort();const c=new AbortController();controller.current=c;
  const n=++generation.current;setReport(null);setError('');setBusy(true);
  const timeout=setTimeout(()=>c.abort(),15000);
  try{const value=await fetchReport(jobId,batchId,uploadId,c.signal);if(n===generation.current)setReport(value);}
  catch{if(n===generation.current)setError('Candidate assessment unavailable. Sign in and reload the saved job.');}
  finally{clearTimeout(timeout);if(n===generation.current)setBusy(false);}
 }
 return h('div',null,h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>void load()},busy?'Loading assessment…':'View consolidated assessment'),
  error&&h('p',{role:'alert'},error),report&&h('button',{type:'button',onClick:()=>{generation.current++;controller.current?.abort();setReport(null);setBusy(false);}},'Close assessment'),report&&h(AssessmentView,{report}));
}
