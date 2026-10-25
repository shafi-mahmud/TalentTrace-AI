import {createElement as h,useEffect,useRef,useState} from 'react';
import {faceRequest,validResult} from '../api/faceWorkflow.ts';
import type {FaceState,FaceResult} from '../api/faceWorkflow.ts';
export default function FaceWorkflowPanel({candidate=false,jobId,interviewId,connected=true}:{candidate?:boolean;jobId?:string;interviewId?:string;connected?:boolean}){
 const [state,setState]=useState<FaceState|null>(null),[receipt,setReceipt]=useState(''),[agreed,setAgreed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<FaceResult|null>(null);
 const generation=useRef(0),pending=useRef(false),scopeInterview=useRef<string|undefined>(interviewId),timerRef=useRef<ReturnType<typeof setInterval>|null>(null),refreshing=useRef<number|null>(null),withdrawing=useRef(false);
 const base=candidate?'interview-access/face-workflow':`jobs/${jobId}/interviews/${interviewId}/face-workflow`;
 async function refresh(n=generation.current){
  if(refreshing.current===n)return;refreshing.current=n;
  try{const v=await faceRequest(base);if(n!==generation.current)return;setState(v);if(v===null&&timerRef.current){clearInterval(timerRef.current);timerRef.current=null;}if(v?.interview_id)scopeInterview.current=v.interview_id;if(!v||v.state!=='enrolled'||v.expires_at*1000<=Date.now())setResult(null);}
  catch{if(n===generation.current){setState(null);setResult(null);}}
  finally{if(refreshing.current===n)refreshing.current=null;}
 }
 useEffect(()=>{const n=++generation.current;setState(null);setReceipt('');scopeInterview.current=interviewId;setAgreed(false);setResult(null);setError('');
  if(!connected||(!candidate&&(!jobId||!interviewId)))return;
  void refresh(n);const timer=setInterval(()=>{if(!pending.current&&!withdrawing.current)void refresh(generation.current);},2000);timerRef.current=timer;
  return()=>{generation.current++;clearInterval(timer);};
 },[candidate,jobId,interviewId,connected]);
 async function withdrawNow(){
  if(withdrawing.current)return;withdrawing.current=true;
  const n=++generation.current;setResult(null);setError('');
  try{
   await faceRequest(receipt?'face-workflow/withdraw':base+'/withdraw',receipt?{interview_id:scopeInterview.current,receipt}:{run_id:state?.run_id});
   if(n===generation.current){setState({state:'withdrawn'});setReceipt('');setAgreed(false);}
  }catch{if(n===generation.current)setError('Withdrawal not confirmed. Ask the recruiter to delete the reference.');}
  finally{withdrawing.current=false;if(n===generation.current)setBusy(false);}
 }
 async function act(action:string,sample?:string){
  if(pending.current)return;pending.current=true;setBusy(true);setError('');setResult(null);const n=++generation.current;
  try{
   const value=action==='withdraw'&&receipt?await faceRequest('face-workflow/withdraw',{interview_id:scopeInterview.current,receipt})
    :await faceRequest(base+'/'+action,action==='consent'?{version:state?.version,accepted:true}:action==='verify'?{run_id:state?.run_id,sample,human_review_confirmed:true}:action==='delete'?{}:{run_id:state?.run_id});
   if(n!==generation.current)return;
   if(action==='verify'){if(!validResult(value))throw Error();const fresh=await faceRequest(base);if(n!==generation.current)return;if(fresh?.state!=='enrolled'||fresh.run_id!==state?.run_id)throw Error();setResult(value);setState(fresh);}
   else{if(value.withdrawal_receipt)setReceipt(value.withdrawal_receipt);if(action==='withdraw'||action==='delete'){setReceipt('');setAgreed(false);}await refresh(n);}
  }catch{if(n===generation.current){setResult(null);setError('Action not confirmed. Refresh before retrying.');}}
  finally{pending.current=false;if(n===generation.current)setBusy(false);}
 }
 if(!state&&!receipt)return null;
 return h('section',{className:'card','aria-label':'Synthetic face reference'},h('h3',null,candidate?'Optional synthetic enrollment':'Synthetic viva review'),
  candidate&&h('p',null,state?.wording??'Synthetic samples only. Manual review is available.'),
  h('p',{role:'status'},state?.state==='enrolled'?'Synthetic reference enrolled':state?.state==='consented'?'Consent recorded':'No active reference'),
  candidate&&!state?.expires_at&&state?.retention_seconds&&h('p',null,`Retention: ${Math.ceil(state.retention_seconds/60)} minutes maximum.`),
  state?.expires_at&&h('p',null,'Expires: '+new Date(state.expires_at*1000).toLocaleString()),
  h('label',null,h('input',{type:'checkbox',checked:agreed,disabled:busy,onChange:(e:any)=>setAgreed(e.target.checked)}),candidate?'I agree to this synthetic-only demonstration.':'I will review this provisional result manually.'),
  candidate&&state?.state==='not_enrolled'&&h('button',{className:'button button-secondary',disabled:busy||!agreed,onClick:()=>void act('consent')},'Consent to synthetic enrollment'),
  candidate&&state?.state==='consented'&&h('button',{className:'button button-primary',disabled:busy||!agreed,onClick:()=>void act('enroll')},'Enroll synthetic sample'),
  candidate&&receipt&&h('button',{className:'button button-secondary',disabled:busy,onClick:()=>{void navigator.clipboard.writeText(JSON.stringify({interview_id:scopeInterview.current,receipt})).catch(()=>setError('Receipt could not be copied. Ask the recruiter to delete the reference.'));}},'Copy withdrawal receipt'),
  candidate&&(receipt||state?.state==='enrolled'||state?.state==='consented')&&h('button',{className:'button button-secondary',onClick:()=>void withdrawNow()},'Withdraw and delete reference'),
  !candidate&&state?.state==='enrolled'&&h('div',null,
   ...['same-design','other-design'].map(sample=>h('button',{key:sample,className:'button button-secondary',disabled:busy||!agreed||!state.viva_authorized,onClick:()=>void act('verify',sample)},sample==='same-design'?'Compare same synthetic design':'Compare other synthetic design')),
   null),
  !candidate&&state&&state.state!=='not_enrolled'&&h('button',{className:'button button-secondary',disabled:busy,onClick:()=>void act('delete')},'Delete reference'),
  result&&h('p',{role:'status'},`Provisional similarity: ${result.similarity.toFixed(4)}. Human review required; identity and liveness are not verified.`),
  error&&h('p',{role:'alert'},error));
}
