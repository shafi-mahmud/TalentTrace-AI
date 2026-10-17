import {createElement as h,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {fetchComparison} from '../api/candidateComparison.ts';
import type {ApplicationIdentity,Comparison} from '../api/candidateComparison';
import {AssessmentView} from './ConsolidatedAssessment.ts';

export function ComparisonView({comparison:c}:{comparison:Comparison}){
 const row=(label:string,values:string[])=>h('tr',{key:label},h('th',{scope:'row'},label),...values.map((v,i)=>h('td',{key:i},v)));
 return h('section',{'aria-label':'Candidate comparison results'},h('h3',null,'Same-job evidence comparison'),h('p',null,c.notice),
  h('div',{className:'comparison-summary'},h('table',null,h('caption',null,'Saved CV requirement coverage and interview availability'),
   h('thead',null,h('tr',null,h('th',{scope:'col'},'Evidence'),h('th',{scope:'col'},'Application A'),h('th',{scope:'col'},'Application B'))),
   h('tbody',null,
    row('Application',c.reports.map(r=>`${r.upload_id} · batch ${r.batch_id}`)),
    row('Criteria revision',c.reports.map(r=>String(r.criteria_revision))),
    row('F2 CV coverage score',c.reports.map(r=>r.cv.score===null?'Not scored':`${r.cv.score.toFixed(2)} / 100`)),
    row('Screening status',c.reports.map(r=>r.cv.screening_decision??'No decision')),
    ...(['skill','experience','education'] as const).map(d=>row(`${d} component`,c.reports.map(r=>{
     const v=r.cv.dimensions.find(x=>x.category===d);return v?`${v.weighted_points.toFixed(2)} points · ${v.weight}% weight · ${v.supported_count}/${v.total_requirements} supported`:'No persisted breakdown';}))),
    row('Interview evidence',c.reports.map(r=>r.interview.state.replaceAll('_',' ')))))),
  h('p',{className:'helper-text'},'A and B reflect your selection order. Review the original questions, evidence, weights and limitations; these are not an automatic ranking.'),
  h('div',{className:'comparison-columns'},...c.reports.map((report,i)=>h('article',{key:report.batch_id+report.upload_id,'aria-label':`Application ${i===0?'A':'B'} assessment`},
   h('h3',null,`Application ${i===0?'A':'B'}`),h(AssessmentView,{report})))));
}

export default function CandidateComparison({jobId,revision,applications}:{jobId:string;revision:number;applications:ApplicationIdentity[]}){
 const [left,setLeft]=useState(''),[right,setRight]=useState(''),[value,setValue]=useState<Comparison|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const sequence=useRef(0),request=useRef<AbortController|null>(null);
 const options=applications;
 const key=(a:ApplicationIdentity)=>`${a.batch_id}/${a.upload_id}`;
 const selected=[options.find(a=>key(a)===left),options.find(a=>key(a)===right)];
 function clear(){sequence.current++;request.current?.abort();setValue(null);setBusy(false);setError('');}
 useLayoutEffect(()=>{clear();setLeft('');setRight('');return()=>{sequence.current++;request.current?.abort();};},[jobId,revision,applications]);
 useEffect(()=>{
  const hidden=()=>{if(document.hidden)clear();};window.addEventListener('hashchange',clear);document.addEventListener('visibilitychange',hidden);
  let timer:ReturnType<typeof setTimeout>|undefined;
  const deadlines=value?.reports.filter(r=>r.interview.state==='available').map(r=>Date.parse(r.interview.retention_deadline!))??[];
  function expire(){const left=Math.min(...deadlines)-Date.now();if(left<=0)clear();else timer=setTimeout(expire,Math.min(left,86400000));}
  if(deadlines.length)expire();
  return()=>{window.removeEventListener('hashchange',clear);document.removeEventListener('visibilitychange',hidden);if(timer!==undefined)clearTimeout(timer);};
 },[value]);
 async function load(){
  if(busy||!selected[0]||!selected[1]||left===right)return;
  clear();const n=sequence.current,c=new AbortController();request.current=c;setBusy(true);
  const timeout=setTimeout(()=>c.abort(),15000);
  try{const result=await fetchComparison(jobId,revision,[selected[0],selected[1]],c.signal);if(n===sequence.current)setValue(result);}
  catch{if(n===sequence.current)setError('Comparison unavailable. Reload the owned job and select current saved applications.');}
  finally{clearTimeout(timeout);if(n===sequence.current)setBusy(false);}
 }
 function selector(label:string,current:string,update:(s:string)=>void){return h('label',null,label,h('select',{value:current,onChange:(e:{target:{value:string}})=>{clear();update(e.target.value);}},
  h('option',{value:''},'Select a saved application'),...options.map((a,i)=>h('option',{key:key(a),value:key(a)},`Saved application ${i+1} · ${a.upload_id.slice(0,8)} · batch ${a.batch_id.slice(0,8)}`))));}
 return h('section',{className:'candidate-comparison','aria-label':'Compare two candidates'},h('h3',null,'Compare two candidates'),
  h('p',null,'Select two saved applications for this job. Retrieval is read-only and does not start AI evaluation.'),
  options.length<2&&h('p',null,'At least two current saved applications are needed.'),
  h('div',{className:'comparison-selectors'},selector('Application A',left,setLeft),selector('Application B',right,setRight)),
  left&&left===right&&h('p',{role:'alert'},'Select two distinct applications.'),
  h('button',{type:'button',className:'button button-secondary',disabled:busy||!left||!right||left===right,onClick:()=>void load()},busy?'Loading comparison…':'Compare selected applications'),
  error&&h('p',{role:'alert'},error),value&&h('button',{type:'button',onClick:clear},'Close comparison'),value&&h(ComparisonView,{comparison:value}));
}
