const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const analysisDisclosure='synthetic-interview-analysis-v1';
export interface AnalysisConfig {enabled:boolean;version:string;disclosure:string;persistence?:string;}
export interface Pair {id:string;question:string;answer:string;question_turns:string[];answer_turns:string[];status:string;warnings:string[];start_ms:number;end_ms:number;capture_id:string;}
export interface Quote {turn_id:string;quote:string;}
export interface Dimension {dimension:string;status:string;justification:string;evidence:Quote[];}
export interface AnalysisResult {provider:string;model:string;rubric_version:string;advisory:boolean;scope:string;asr_review:string;warning:string;criteria_revision:number;
  outcome?:'needs_review'|'assessed';inference_performed?:boolean;
  pairs:Pair[];requirements:{criterion_id:string;description:string;coverage:string;explanation:string;follow_up:string;qa_ids:string[];turn_ids:string[]}[];
  assessment:{answers:{qa_id:string;dimensions:Dimension[];technical_citations:{reference_id:string;quote:string}[];follow_up:string}[]};
  technical_references:{id:string;topic:string;text:string;provenance:string;source_title?:string;document_id?:string;url?:string;location?:string;version?:string;retrieval_basis?:string}[];
  turns:{id:string;role:string;text:string;session_id:string;start_ms:number;end_ms:number}[];unpaired_turn_ids:string[];
  strengths:{qa_id:string;dimension:string;interpretation:string;evidence:Quote[]}[];
  gaps:{criterion_id:string;coverage:string;follow_up:string}[];}
export interface AnalysisOperation {operation_id:string;status:'running'|'completed'|'failed'|'unavailable';error:string|null;persistence:string;attempt?:number;result:AnalysisResult|null;}
async function request(path:string,body?:unknown,revision?:number){
  const response=await fetch(base+'/api/v1'+path,{credentials:'include',cache:'no-store',method:body===undefined?'GET':'POST',
    headers:{'X-TalentTrace-Request':'1',...(body===undefined?{}:{'Content-Type':'application/json','X-TalentTrace-Evaluation-Disclosure':analysisDisclosure,'X-TalentTrace-Job-Revision':String(revision)})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok)throw Error('Analysis unavailable or unconfirmed. Check status; do not automatically repeat.');
  return await response.json();
}
function path(job:string,interview:string){if(!uuid.test(job)||!uuid.test(interview))throw Error('Select a saved interview.');return `/jobs/${job}/interviews/${interview}/analysis`;}
export async function analysisConfig():Promise<AnalysisConfig>{const v=await request('/interview-analysis/config');
  if(typeof v?.enabled!=='boolean'||v.version!==analysisDisclosure||typeof v.disclosure!=='string')throw Error('Analysis configuration unavailable.');return v;}
export function isAnalysisOperation(v:any):v is AnalysisOperation{
  if(!uuid.test(v?.operation_id??'')||!['running','completed','failed','unavailable'].includes(v.status)||!['ephemeral_single_worker','postgresql_privacy_bound'].includes(v.persistence))return false;
  if(v.persistence==='postgresql_privacy_bound'&&(!Number.isInteger(v.attempt)||v.attempt<1))return false;
  if(v.status!=='completed')return v.result===null;
  const r=v.result;
  const text=(s:unknown,max=2000)=>typeof s==='string'&&s.length<=max;
  const ids=(a:any)=>Array.isArray(a)&&a.length<=1500&&a.every((id:any)=>typeof id==='string'&&uuid.test(id));
  const quotes=(a:any)=>Array.isArray(a)&&a.length<=8&&a.every((q:any)=>uuid.test(q?.turn_id??'')&&text(q.quote,1000));
  return !!r&&r.advisory===true&&r.scope==='accepted_audio_only'&&r.asr_review==='unverified'
    &&typeof r.provider==='string'&&typeof r.model==='string'&&typeof r.warning==='string'
    &&r.rubric_version==='interview-evidence-v1'&&Array.isArray(r.pairs)&&r.pairs.length<=50
    &&r.pairs.every((p:any)=>uuid.test(p.id)&&typeof p.question==='string'&&typeof p.answer==='string'
      &&ids(p.question_turns)&&ids(p.answer_turns)&&Array.isArray(p.warnings)&&p.warnings.every((w:any)=>text(w))
      &&['answered','unanswered','uncertain'].includes(p.status)&&Number.isInteger(p.start_ms)&&Number.isInteger(p.end_ms)&&p.end_ms>=p.start_ms)
    &&Array.isArray(r.turns)&&r.turns.length<=1500&&r.turns.every((t:any)=>uuid.test(t.id)&&['candidate','recruiter'].includes(t.role)&&typeof t.text==='string')
    &&Array.isArray(r.requirements)&&r.requirements.length<=50&&r.requirements.every((m:any)=>text(m?.criterion_id,64)&&text(m.description,500)
      &&['partial','not_evidenced','uncertain'].includes(m.coverage)&&text(m.explanation)&&text(m.follow_up)&&ids(m.qa_ids)&&ids(m.turn_ids))
    &&Array.isArray(r.technical_references)&&r.technical_references.length<=10&&r.technical_references.every((t:any)=>text(t?.id,100)&&text(t.text)&&text(t.topic)&&['synthetic_demo','official_documentation_summary'].includes(t.provenance)
      &&(t.provenance!=='official_documentation_summary'||['source_title','document_id','url','location','version','retrieval_basis'].every(key=>text(t[key],1000)&&t[key].length>0)))
    &&Array.isArray(r.strengths)&&r.strengths.length<=200&&r.strengths.every((s:any)=>uuid.test(s?.qa_id??'')&&text(s.dimension)&&text(s.interpretation)&&quotes(s.evidence))
    &&Array.isArray(r.gaps)&&r.gaps.length<=50&&r.gaps.every((g:any)=>text(g?.criterion_id)&&text(g.coverage)&&text(g.follow_up))&&ids(r.unpaired_turn_ids)
    &&Array.isArray(r.assessment?.answers)&&r.assessment.answers.length===r.pairs.length
    &&r.assessment.answers.every((a:any)=>uuid.test(a.qa_id)&&Array.isArray(a.dimensions)&&a.dimensions.length===4
      &&text(a.follow_up)&&Array.isArray(a.technical_citations)&&a.technical_citations.length<=5&&a.technical_citations.every((c:any)=>text(c?.reference_id)&&text(c.quote,1000))
      &&a.dimensions.every((d:any)=>['relevance','technical_accuracy','completeness','articulation'].includes(d.dimension)
        &&['supported','partial','concern','uncertain','not_assessed'].includes(d.status)&&text(d.justification,800)&&quotes(d.evidence)));
}
export async function startAnalysis(job:string,interview:string,revision:number,id:string,retryAttempt?:number):Promise<AnalysisOperation>{
  if(!uuid.test(id)||!Number.isInteger(revision)||revision<1)throw Error('Invalid analysis context.');
  const v=await request(path(job,interview),{operation_id:id,...(retryAttempt===undefined?{}:{retry_failed:true,expected_attempt:retryAttempt})},revision);if(!isAnalysisOperation(v))throw Error('Analysis response invalid.');return v;
}
export async function analysisStatus(job:string,interview:string,id:string):Promise<AnalysisOperation>{
  if(!uuid.test(id))throw Error('Invalid operation identity.');const v=await request(path(job,interview)+'/'+id);
  if(!isAnalysisOperation(v))throw Error('Analysis response invalid.');return v;
}
