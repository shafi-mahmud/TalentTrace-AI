import {createElement as h} from 'react';
import type {ReactNode} from 'react';
import type {ConsolidatedReport} from '../api/consolidatedAssessment';

const cvLabels={supported:'Demonstrated in saved CV',not_found:'Not demonstrated in saved CV',ambiguous:'Uncertain CV evidence'};
const interviewLabels:Record<string,string>={partial:'Literal topic evidence; competence not established',not_evidenced:'No literal topic evidence; semantic coverage not assessed',uncertain:'Uncertain topic evidence; verification needed'};

/** A source index, not an assessment engine. Only already-authorized report data. */
export default function SuitabilityEvidence({report:r,link}:{report:ConsolidatedReport;link:(id:string,text:string)=>ReactNode}){
 const matches=r.cv.dimensions.flatMap(d=>d.matches);
 const interview=r.interview.state==='available'?r.interview:null;
 const requirements=r.confirmed_requirements;
 const ids=[...new Set([...requirements.map(c=>c.criterion_id),...matches.map(m=>m.criterion_id),...(interview?.requirements.map(m=>m.criterion_id)??[])])];
 const findings=interview?.assessment?.answers.flatMap(a=>a.dimensions)??[];
 const cvCount=matches.filter(m=>m.match_status==='supported').length;
 return h('section',{'aria-label':'Suitability evidence profile',className:'suitability-evidence'},
  h('h4',null,'Suitability evidence profile'),
  h('p',null,h('strong',null,r.confirmation?.state==='confirmed'?'Overall suitability position: recruiter-confirmed; reviewed scope and rationale follow below.':
   r.confirmation?.state==='stale'?'Overall suitability position: stale; fresh recruiter confirmation required.':
   r.confirmation?.state==='restricted'?'Overall suitability position: restricted; no active judgment is disclosed.':'Overall suitability position: pending recruiter confirmation.')),
  h('p',null,'This system-assembled evidence profile is not a suitability judgment or hiring recommendation.'),
  h('dl',null,
   h('dt',null,'CV score'),h('dd',null,r.cv.score===null?'Not scored; no numerical value is substituted.':`${r.cv.score.toFixed(2)} / 100 — existing F2 weighted CV requirement coverage.`),
   h('dt',null,'Interview findings'),h('dd',null,interview?'Saved qualitative F5 interpretations; ASR remains unverified.':`Source status: ${r.interview.state.replaceAll('_',' ')}. Missing or restricted evidence is not poor performance.`),
   h('dt',null,'Evidence completeness'),h('dd',null,
    matches.length?`${cvCount} supported CV matches among ${matches.length} persisted CV requirement matches. `:'No persisted CV requirement matches; CV evidence completeness cannot be calculated. ',
    interview?`${interview.pairs.length} authorized question/answer pairs. `:'No authorized interview pairs are available. ',
    'These counts describe available records, not candidate quality.')),
  !requirements.length&&h('p',null,'Confirmed requirement descriptions for this report revision are unavailable. Historical IDs are retained for audit; current names are not substituted.'),
  r.cv.dimensions.length===0&&h('p',null,'Requirement-level CV matches were not persisted for this unscored result. No per-requirement CV conclusion can be reconstructed.'),
  findings.length>0&&h('p',null,`Recorded F5 dimension findings: ${findings.filter(d=>d.status==='supported').length} supported; ${findings.filter(d=>d.status==='concern').length} concern; ${findings.filter(d=>d.status==='partial').length} partial; ${findings.filter(d=>d.status==='uncertain'||d.status==='not_assessed').length} uncertain or not assessed. Original justifications and source quotations follow below; these are not overall ratings.`),
  ids.length>0?h('div',{className:'evidence-table-scroll'},h('table',{className:'evidence-profile-table'},
   h('caption',null,'Requirement evidence and verification index'),
   h('thead',null,h('tr',null,...['Confirmed requirement','CV evidence','Interview topic / assessed questions','Recruiter verification'].map(v=>h('th',{key:v,scope:'col'},v)))),
   h('tbody',null,...ids.map(id=>{
    const criterion=requirements.find(c=>c.criterion_id===id),cv=matches.find(m=>m.criterion_id===id),f5=interview?.requirements.find(m=>m.criterion_id===id);
    return h('tr',{key:id},
     h('th',{scope:'row'},criterion?.description??f5?.description??'Saved CV requirement (description unavailable)',criterion&&h('small',null,criterion.is_hard?'Mandatory requirement':'Preferred requirement'),h('details',null,h('summary',null,'Requirement audit ID'),h('code',null,id))),
     h('td',null,cv?link(`cv-${id}`,cvLabels[cv.match_status]):'No persisted CV requirement evidence'),
     h('td',null,f5?h('div',null,h('p',null,interviewLabels[f5.coverage]),...f5.qa_ids.map(qa=>link(`qa-${qa}`,interview!.pairs.find(p=>p.id===qa)?.question??'Saved question (label unavailable)'))):interview?'No saved interview mapping; not assessed.':'Interview evidence unavailable for assessment.'),
     h('td',null,f5?.follow_up??(cv?.match_status==='supported'?'Review original CV evidence and verify interview coverage.':'Verify this requirement directly; missing records do not establish a weakness.')));
   })))):h('p',null,'No requirement-level evidence index can be assembled from the available records.'),
  h('p',{className:'helper-text'},'Interview topic coverage does not establish competence. Documented concerns and strengths below are advisory findings tied to individual answers; no combined score or automatic decision is calculated.'));
}
