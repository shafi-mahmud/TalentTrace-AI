import {createElement as h,useLayoutEffect,useRef,useState} from 'react';
import {fetchApplications} from '../api/applicationDiscovery.ts';
import type {ApplicationDiscovery as Discovery} from '../api/applicationDiscovery';
import ConsolidatedAssessment from './ConsolidatedAssessment.ts';
import CandidateComparison from './CandidateComparison.ts';

export function DiscoveryCards({discovery:d}:{discovery:Discovery}){
 return h('div',null,h('p',{className:'helper-text'},d.notice),
  d.applications.length===0&&h('p',null,'No persisted application evidence records found. This does not establish that no CV files exist.'),
  ...d.applications.map(a=>h('article',{key:a.batch_id+a.upload_id,className:'candidate-card'},
   h('h4',null,a.label),h('p',null,`Application ${a.upload_id} · batch ${a.batch_id}`),h('p',null,a.detail),
   h('p',null,`Recorded criteria revisions: ${a.recorded_revisions.join(', ')||'not established'}`),
   !a.comparison_available&&h('p',{className:'helper-text'},'Not comparable with current confirmed criteria and weights.'),
   a.report_available?h(ConsolidatedAssessment,{jobId:d.job_id,batchId:a.batch_id,uploadId:a.upload_id}):h('p',null,'No validated report available; no evidence is reconstructed.'))));
}

export default function ApplicationDiscovery({jobId,revision}:{jobId:string;revision:number}){
 const [value,setValue]=useState<Discovery|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const generation=useRef(0),request=useRef<AbortController|null>(null);
 useLayoutEffect(()=>{generation.current++;request.current?.abort();setValue(null);setError('');setBusy(false);
  return()=>{generation.current++;request.current?.abort();};},[jobId,revision]);
 async function load(){
  request.current?.abort();const c=new AbortController();request.current=c;const n=++generation.current;setValue(null);setError('');setBusy(true);
  const timer=setTimeout(()=>c.abort(),15000);
  try{const v=await fetchApplications(jobId,revision,c.signal);if(n===generation.current)setValue(v);}
  catch{if(n===generation.current)setError('Application evidence unavailable. Reload the owned job.');}
  finally{clearTimeout(timer);if(n===generation.current)setBusy(false);}
 }
 return h('section',{'aria-label':'Application evidence discovery'},h('h3',null,'Application evidence'),
  h('p',null,'Discover saved scores, unscored decisions and preserved interview selection snapshots. This does not run screening.'),
  h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>void load()},busy?'Loading applications…':'Load application evidence'),
  error&&h('p',{role:'alert'},error),value&&h(CandidateComparison,{jobId,revision,applications:value.applications.filter(a=>a.comparison_available)}),
  value&&h(DiscoveryCards,{discovery:value}));
}
