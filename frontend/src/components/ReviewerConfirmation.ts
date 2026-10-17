import {createElement as h,useState} from 'react';
import type {ConsolidatedReport} from '../api/consolidatedAssessment';
import {positionLabels,reasonLabels,saveConfirmation} from '../api/reviewerConfirmation.ts';
import type {EvidenceReference,Position,Scope} from '../api/reviewerConfirmation';

export function confirmationChoices(r:ConsolidatedReport,scope:Scope):{ref:EvidenceReference;label:string}[]{
 const choices:{ref:EvidenceReference;label:string}[]=[];
 for(const c of r.confirmed_requirements){
  const match=r.cv.dimensions.flatMap(d=>d.matches).find(m=>m.criterion_id===c.criterion_id);
  if(match)choices.push({ref:{criterion_id:c.criterion_id,kind:'cv',reason:match.match_status==='supported'?'supported_requirement':match.match_status==='ambiguous'?'uncertain_finding':'missing_evidence',qa_id:null,dimension:null},label:`${c.description} — saved CV: ${match.match_status.replaceAll('_',' ')}`});
  choices.push({ref:{criterion_id:c.criterion_id,kind:'gap',reason:'missing_evidence',qa_id:null,dimension:null},label:`${c.description} — missing/unassessed evidence (validated when confirming)`});
  if(scope==='cv_interview'&&r.interview.state==='available'){
   const mapping=r.interview.requirements.find(m=>m.criterion_id===c.criterion_id);
   for(const a of r.interview.assessment!.answers.filter(a=>mapping?.qa_ids.includes(a.qa_id))){
    for(const d of a.dimensions){
     if(d.status==='supported'&&(!['technical_accuracy','completeness'].includes(d.dimension)||mapping?.coverage!=='partial'))continue;
     const reason=d.status==='supported'?'supported_requirement':d.status==='concern'?'documented_concern':d.status==='not_assessed'?'missing_evidence':'uncertain_finding';
     choices.push({ref:{criterion_id:c.criterion_id,kind:'interview',reason,qa_id:a.qa_id,dimension:d.dimension},label:`${c.description} — ${r.interview.pairs.find(p=>p.id===a.qa_id)?.question} — ${d.dimension.replaceAll('_',' ')}: ${d.status}`});
    }
   }
  }
 }
 return choices;
}
export function ConfirmationSummary({report:r}:{report:ConsolidatedReport}){
 const c=r.confirmation;if(!c||c.state!=='confirmed')return null;
 return h('section',{'aria-label':'Recruiter-confirmed suitability'},h('h4',null,'Recruiter-confirmed suitability'),
  h('p',null,positionLabels[c.position!]),h('p',null,c.scope==='cv_only'?'CV-only reviewed scope; interview evidence is not part of this judgment.':'Reviewed CV and authorized interview evidence.'),
  h('p',null,'This is a reviewer judgment, separate from evidence completeness and a hiring decision.'),
  h('p',null,`Reviewed requirements: ${c.requirement_ids.map(id=>r.confirmed_requirements.find(v=>v.criterion_id===id)?.description??id).join('; ')}`),
  h('p',null,`Confirmed ${c.confirmed_at} · expires ${c.expires_at} · reviewer ${c.reviewer_id} · version ${c.version}`),
  h('ul',null,...c.references.map((ref,n)=>h('li',{key:n},`${r.confirmed_requirements.find(v=>v.criterion_id===ref.criterion_id)?.description??ref.criterion_id} — ${reasonLabels[ref.reason]} (${ref.kind})`))),
  h('details',null,h('summary',null,'Reviewed evidence audit references'),...c.references.map((ref,n)=>h('p',{key:n},`${ref.criterion_id} · ${ref.kind} · ${ref.reason}${ref.qa_id?` · question ${ref.qa_id} · ${ref.dimension}`:''}`))));
}
export default function ReviewerConfirmation({report:r,refresh,signal}:{report:ConsolidatedReport;refresh:()=>void;signal:AbortSignal}){
 const [position,setPosition]=useState<Position|''>(''),[scope,setScope]=useState<Scope>('cv_only');
 const [ids,setIds]=useState<string[]>(r.confirmed_requirements.filter(c=>c.is_hard).map(c=>c.criterion_id));
 const [selected,setSelected]=useState<string[]>([]),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[locked,setLocked]=useState(false),[message,setMessage]=useState('');
 const c=r.confirmation;if(!c?.enabled)return null;
 const choices=confirmationChoices(r,scope);
 async function submit(){
  if(!position||!ack||locked||busy||!c?.evidence_token)return;
  setBusy(true);setLocked(true);setMessage('');
  try{await saveConfirmation(r.job_id,r.batch_id,r.upload_id,{expected_version:c.version,evidence_token:c.evidence_token,position:position as Position,scope,requirement_ids:ids,references:choices.filter(v=>ids.includes(v.ref.criterion_id)&&selected.includes(JSON.stringify(v.ref))).map(v=>v.ref)},signal);
   if(!signal.aborted)refresh();}
  catch{if(!signal.aborted)setMessage('Confirmation outcome was not verified. Refresh the report and reconcile before confirming again. No automatic retry was made.');}
  finally{if(!signal.aborted)setBusy(false);}
 }
 return h('section',{'aria-label':'Confirm reviewed suitability'},h('h4',null,'Confirm reviewed suitability'),
  h('p',null,'Choose an explicit scope and evidence-linked reasons. All mandatory requirements must remain in scope. No free-text rationale is stored.'),
  h('label',null,'Reviewed sources',h('select',{value:scope,disabled:locked,onChange:(e:{target:{value:string}})=>{setScope(e.target.value as Scope);setSelected([]);}},
   h('option',{value:'cv_only'},'CV only'),h('option',{value:'cv_interview',disabled:r.interview.state!=='available'},'CV and interview'))),
  h('label',null,'Reviewer position',h('select',{value:position,disabled:locked,onChange:(e:{target:{value:string}})=>setPosition(e.target.value as Position)},
   h('option',{value:''},'Select a position'),...Object.entries(positionLabels).map(([v,label])=>h('option',{key:v,value:v},label)))),
  h('fieldset',null,h('legend',null,'Reviewed requirements'),...r.confirmed_requirements.map(v=>h('label',{key:v.criterion_id},h('input',{type:'checkbox',checked:ids.includes(v.criterion_id),disabled:v.is_hard||locked,onChange:()=>setIds(ids.includes(v.criterion_id)?ids.filter(x=>x!==v.criterion_id):[...ids,v.criterion_id])}),v.description,v.is_hard?' (mandatory)':''))),
  h('fieldset',null,h('legend',null,'Structured rationale and original evidence'),...choices.filter(v=>ids.includes(v.ref.criterion_id)).map(v=>{const key=JSON.stringify(v.ref);return h('label',{key},h('input',{type:'checkbox',checked:selected.includes(key),disabled:locked,onChange:()=>setSelected(selected.includes(key)?selected.filter(x=>x!==key):[...selected,key])}),v.label);})),
  h('label',null,h('input',{type:'checkbox',checked:ack,disabled:locked,onChange:()=>setAck(!ack)}),'I reviewed the original evidence and limitations. This is not a hire/reject decision.'),
  h('button',{type:'button',disabled:busy||locked||!ack||!position||!ids.length||!selected.length||!c.evidence_token,onClick:()=>void submit()},busy?'Confirming…':'Confirm reviewed suitability'),
  message&&h('p',{role:'alert'},message),locked&&h('button',{type:'button',onClick:refresh},'Refresh and reconcile current state'));
}
