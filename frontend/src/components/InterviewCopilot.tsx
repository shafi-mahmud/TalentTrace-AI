import {useEffect,useRef,useState} from 'react';
import * as api from '../api/copilot';
import type {Context,Status} from '../api/copilot';

export default function InterviewCopilot({candidate,jobId,interviewId,connected}:Context&{connected:boolean}){
  const [enabled,setEnabled]=useState<boolean|null>(null);const [wording,setWording]=useState('');const [liveEnabled,setLiveEnabled]=useState(false);
  const [value,setValue]=useState<Status|null>(null);const [agreed,setAgreed]=useState(false);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const [syntheticCloud,setSyntheticCloud]=useState(false);
  const fence=useRef(new api.ResponseFence());const inflight=useRef<number|null>(null);
  const current=useRef<Status|null>(null);const context:Context={candidate,jobId,interviewId};
  function accept(v:Status){
    if(current.current?.run_id!==v.run_id||current.current?.epoch!==v.epoch)setAgreed(false);
    current.current=v;setValue(v);setError('');
  }
  async function refresh(){
    if(inflight.current||!connected)return;
    const ticket=fence.current.next();inflight.current=ticket;
    try{const v=await api.status(context);if(fence.current.accepts(ticket))accept(v);}
    catch{if(fence.current.accepts(ticket)){current.current=null;setValue(null);setAgreed(false);setError('Assistant unavailable. No suggestion is assumed.');}}
    finally{if(inflight.current===ticket)inflight.current=null;}
  }
  useEffect(()=>{
    let active=true;fence.current.clear();setValue(null);current.current=null;setAgreed(false);setEnabled(null);
    void api.config().then(v=>{if(active){setEnabled(v.enabled);setWording(v.wording);setLiveEnabled(v.live_enabled===true);setSyntheticCloud(v.synthetic_cloud===true);}})
      .catch(()=>{if(active)setError('Assistant configuration unavailable.');});
    return()=>{active=false;fence.current.clear();};
  },[candidate,jobId,interviewId]);
  useEffect(()=>{
    if(!enabled||!connected){fence.current.clear();setValue(null);setAgreed(false);return;}
    void refresh();const timer=window.setInterval(()=>void refresh(),2000);
    return()=>{
      window.clearInterval(timer);fence.current.clear();inflight.current=null;
      const last=current.current;current.current=null;
      // Best effort on leave/navigation. Server TTL is the backstop, never a
      // guarantee that a closed browser delivered this withdrawal.
      if(last?.run_id&&last.status!=='withdrawn')void api.decide(context,last,'withdraw').catch(()=>{});
    };
  },[enabled,connected,candidate,jobId,interviewId]);
  useEffect(()=>{
    if(!value)return;
    const timer=window.setTimeout(()=>{fence.current.clear();current.current=null;setValue(null);setAgreed(false);},value.expires_in_ms);
    return()=>window.clearTimeout(timer);
  },[value]);
  async function action(kind:'prepare'|'accept'|'decline'|'withdraw'|'dismiss'){
    // Dismissal, like withdrawal, must fence a slow poll before it can repaint advice.
    if((inflight.current&&kind!=='withdraw'&&kind!=='decline'&&kind!=='dismiss')||busy||!connected)return;
    const snapshot=current.current;
    if(kind==='accept'&&!agreed)return;
    const ticket=fence.current.next();inflight.current=ticket;setBusy(true);setValue(null);setAgreed(false);
    try{
      const v=kind==='prepare'?await api.prepare(context):!snapshot?null:kind==='dismiss'?await api.dismiss(context,snapshot):await api.decide(context,snapshot,kind);
      if(fence.current.accepts(ticket)&&v)accept(v);
    }catch{if(fence.current.accepts(ticket)){current.current=null;setValue(null);setError('Operation unconfirmed. Check assistant status before another action.');}}
    finally{if(inflight.current===ticket)inflight.current=null;setBusy(false);}
  }
  const own=candidate?value?.candidate_consented:value?.recruiter_consented;
  return <section className="card" aria-label={candidate?'Interview assistant consent':'Interviewer co-pilot'}>
    <h2>{candidate?'Interview assistant consent':'Interviewer co-pilot'}</h2>
    <p>{syntheticCloud?"Fixed synthetic AssemblyAI captions feed the local F11 assistant. No physical microphone upload. Prepare this run and obtain both independent consents before replay.":liveEnabled?"Local F4 adapter enabled. Connect both caption participants, prepare this run and independently consent before synthetic speech. Recognition and relevance are not guaranteed.":"Live suggestions are not connected. Internal synthetic tests only."}</p>
    {error&&<p role="alert">{error}</p>}
    {enabled===null?<p>Assistant configuration unavailable.</p>:!enabled?<p>Interview assistant is disabled.</p>:<>
      <p>{wording}</p><p role="status">{!connected?'Join the interview to review consent.':value?`Assistant: ${value.status}`:'Assistant status unavailable.'}</p>
      <button disabled={!connected||busy} onClick={()=>void refresh()}>Check assistant status</button>
      {!candidate&&<button disabled={!connected||busy} onClick={()=>void action('prepare')}>Prepare new assistant run</button>}
      {connected&&value?.run_id&&value.status!=='withdrawn'&&<>
        <p>Recruiter consent: {value.recruiter_consented?'yes':'no'}; Candidate consent: {value.candidate_consented?'yes':'no'}. Storage and caption consent are separate.</p>
        {!own&&<><label><input type="checkbox" checked={agreed} disabled={busy} onChange={e=>setAgreed(e.target.checked)}/> {syntheticCloud?"I agree to temporary assistant processing of fixed synthetic AssemblyAI captions, with separate cloud-caption consent and possible provider model-training use.":"I agree to temporary local interview-assistant processing."}</label>
          <button disabled={!connected||busy||!agreed} onClick={()=>void action('accept')}>Agree to assistant processing</button>
          <button disabled={!connected||busy} onClick={()=>void action('decline')}>Decline assistant processing</button></>}
        <button disabled={!connected||busy} onClick={()=>void action('withdraw')}>Withdraw assistant consent</button>
      </>}
      {!candidate&&connected&&value?.status==='authorized'&&(value.suggestion?<article aria-label="Provisional question suggestion">
        <h3>Provisional follow-up</h3><p>{value.suggestion.question}</p><p>Requirement: {value.suggestion.requirement}</p><p>{value.suggestion.reason}</p>
        <button disabled={busy} onClick={()=>void action('dismiss')}>Dismiss / Ignore</button></article>:<p>{value.live_connected?"Waiting for authorized recognized speech or an eligible follow-up.":"Waiting for context. Live speech is not connected."}</p>)}
    </>}
  </section>;
}
