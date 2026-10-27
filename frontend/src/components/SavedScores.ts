import ApplicationDiscovery from './ApplicationDiscovery.ts';
import ConsolidatedAssessment from './ConsolidatedAssessment.ts';
import {createElement as h,useLayoutEffect,useRef,useState} from 'react';
import {authenticatedFetch} from '../api/session.ts';
import {validSavedBatches} from '../api/savedScoreValidation.ts';
export {validSavedBatches} from '../api/savedScoreValidation.ts';
import type {ScoringBatch, CandidateScore} from '../types/screening';
import {ScoreDetails,ScoringProvenance} from './scorePresentation.ts';
export async function fetchSavedBatches(job:string,revision:number){
 const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const response=await authenticatedFetch(`${base}/api/v1/jobs/${job}/scores`,{signal:controller.signal});if(!response.ok)throw new Error('Saved scores unavailable. Sign in and reload confirmed job criteria.');const value:unknown=await response.json();if(!validSavedBatches(value,job,revision))throw new Error('Saved score associations could not be validated.');return value;}catch{throw new Error('Saved scores unavailable. Sign in and reload confirmed job criteria.');}finally{clearTimeout(timer);}
}
export function SavedScoreCards({batches,onSelect}:{batches:ScoringBatch[];onSelect:(b:ScoringBatch,c:CandidateScore)=>void}){return h('div',null,...batches.flatMap((b,bi)=>b.candidates.map((c,ci)=>h('article',{key:b.batch_id+c.upload_id,className:'candidate-card'},h('h3',null,`Saved candidate ${bi+1}.${ci+1}`),h('p',null,`Candidate reference: ${c.upload_id.slice(0,8)}`),h('p',null,`${c.screening_decision??'No decision'} · criteria revision ${b.criteria_revision}`),h(ScoringProvenance,{provenance:b.ai_provenance}),h(ScoreDetails,{score:c}),h('details',null,h('summary',null,'Saved requirement evidence'),...c.dimensions.flatMap(d=>d.matches.map(m=>h('div',{key:m.criterion_id},h('p',null,`${d.category} · ${m.match_status}`),h('p',null,m.explanation),...m.evidence.map((e,i)=>h('p',{key:i},`${e.value} — ${e.source.kind} ${e.source.number} · ${e.source.method}`)))))),h(ConsolidatedAssessment,{jobId:b.job_id,batchId:b.batch_id,uploadId:c.upload_id}),h('button',{type:'button',className:'button button-secondary',disabled:c.screening_decision!=='eligible',onClick:()=>onSelect(b,c)},'Select for interview')))));}
export interface InterviewSelection {batch:ScoringBatch;candidate:CandidateScore}
export default function SavedScores({jobId,revision,onSelectCandidate}:{jobId:string;revision:number;onSelectCandidate:(selection:InterviewSelection)=>void}){
 const [batches,setBatches]=useState<ScoringBatch[]|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);const generation=useRef(0),pending=useRef(false);
 useLayoutEffect(()=>{generation.current++;setBatches(null);setError('');setBusy(false);pending.current=false;return()=>{generation.current++;};},[jobId,revision]);
 async function load(){if(pending.current)return;pending.current=true;setBusy(true);setError('');const n=++generation.current;try{const v=await fetchSavedBatches(jobId,revision);if(n===generation.current)setBatches(v);}catch(e){if(n===generation.current)setError((e as Error).message);}finally{if(n===generation.current){pending.current=false;setBusy(false);}}}
 return h('section',{className:'card saved-scores','aria-label':'Previously saved scores'},h('h2',null,'Previously saved candidate scores'),h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>void load()},busy?'Loading…':'Load saved scores'),h('p',null,'Loading saved scores is read-only and makes no CV upload or AI call.'),error&&h('p',{role:'alert'},error),h(ApplicationDiscovery,{jobId,revision}),batches&&h(SavedScoreCards,{batches,onSelect:(batch,candidate)=>onSelectCandidate({batch,candidate})}),batches?.length===0&&h('p',null,'No saved results for this revision.'));
}
