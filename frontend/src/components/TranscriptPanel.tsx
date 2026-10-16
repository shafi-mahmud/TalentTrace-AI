import {useEffect,useState} from 'react';
import {storageConfig,prepareStorage,storageDecision,privacyStatus,withdrawStorage,reviewTranscript} from '../api/transcripts';
import type {TranscriptContext,StorageConfig,Setup,PrivacyStatus,TranscriptReview} from '../api/transcripts';

export default function TranscriptPanel({candidate=false,jobId,interviewId,connected=false,privacyOnly=false,onAvailability}:
  TranscriptContext & {connected?:boolean;privacyOnly?:boolean;onAvailability?:(available:boolean)=>void}) {
  const context={candidate,jobId,interviewId};
  const [config,setConfig]=useState<StorageConfig|null>(null),[setup,setSetup]=useState<Setup|null>(null);
  const [status,setStatus]=useState<PrivacyStatus|null>(null),[review,setReview]=useState<TranscriptReview|null>(null);
  const [checked,setChecked]=useState(false),[accepted,setAccepted]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('Storage disabled until both participants independently consent.');
  useEffect(()=>{let live=true;setSetup(null);setReview(null);setStatus(null);setAccepted(false);setChecked(false);
    void storageConfig().then(v=>{if(live){setConfig(v);onAvailability?.(v.enabled);}})
      .catch(()=>{if(live)setMessage('Optional storage is unavailable. Temporary captions remain separate.');});
    return()=>{live=false;};},[candidate,jobId,interviewId]);
  async function refresh(){try{const v=await privacyStatus(context);setStatus(v);
    if(v.withdrawn || v.expired){setReview(null);setAccepted(false);}
  }catch{setReview(null);setMessage('Storage status unavailable. No saved transcript is assumed.');}}
  useEffect(()=>{if(!config?.enabled || (!setup && !review && !privacyOnly))return;
    void refresh();const timer=setInterval(()=>void refresh(),3000);return()=>clearInterval(timer);
  },[config?.enabled,setup?.capture_id,!!review,candidate,jobId,interviewId,privacyOnly]);
  async function act(action:()=>Promise<void>){if(busy)return;setBusy(true);try{await action();}
    catch{setReview(null);setMessage('Operation unconfirmed. Check status before another attempt; no automatic retry was sent.');}finally{setBusy(false);}}
  if(!config?.enabled)return <section aria-label="Transcript storage"><p>Optional transcript storage is disabled or unavailable. Temporary captions remain usable.</p></section>;
  const blocked=!!status?.withdrawn || !!status?.expired;
  return <section aria-label="Transcript storage"><h2>Optional interview transcript</h2>
    {!privacyOnly && <p>Review storage consent before starting captions. Without both consents, captions remain temporary. No audio or video recording.</p>}
    {!privacyOnly && !setup && <button disabled={!connected || busy} onClick={()=>void act(async()=>{setSetup(await prepareStorage(context));setMessage('Review the separate storage disclosure.');})}>Review optional storage consent</button>}
    {!privacyOnly && setup && !blocked && <><p style={{whiteSpace:'pre-wrap'}}>{config.wording}</p>
      <label><input type="checkbox" checked={checked} disabled={accepted || busy} onChange={e=>setChecked(e.target.checked)}/> I agree to optional transcript storage.</label>
      <button disabled={!checked || accepted || busy} onClick={()=>void act(async()=>{await storageDecision(context,setup.capture_id,'accept');setAccepted(true);setMessage('Your consent was received. Authorization alone does not mean text was saved.');await refresh();})}>Accept transcript storage</button>
      <button disabled={busy || accepted} onClick={()=>void act(async()=>{await storageDecision(context,setup.capture_id,'decline');setMessage('Storage declined. Temporary captions may continue.');await refresh();})}>Decline storage</button></>}
    <p role="status">{message}</p>
    {status && <p>{status.deletion_verified?'Deleted — verified.':status.withdrawn?`Withdrawal received; deletion ${status.deletion_status}.`:status.expired?'Retention expired; transcript unavailable.':status.capture_status==='completed'&&status.persistence_outcome==='saved'?'Transcript saved for accepted audio only.':status.capture_status==='active'?'Both participants consented; capture authorized. Saving is not yet confirmed.':status.capture_status==='interrupted'?'Transcript incomplete.':'Storage disabled or awaiting both consents.'}
      {status.retention_deadline && ` Retention deadline: ${new Date(status.retention_deadline).toLocaleString()}.`}</p>}
    <button disabled={busy} onClick={()=>void refresh()}>Check transcript status</button>
    <button disabled={busy || !!status?.deletion_verified} onClick={()=>void act(async()=>{setReview(null);await withdrawStorage(context);setMessage('Withdrawal requested. Deletion is complete only when verified below.');await refresh();})}>Withdraw consent and request deletion</button>
    {!candidate && !privacyOnly && <button disabled={busy || blocked} onClick={()=>void act(async()=>{setReview(await reviewTranscript(context));})}>Load saved transcript</button>}
    {review && <div><p>{review.warning}</p>{review.captures.map(c=><p key={c.id}>{c.status==='completed'&&c.outcome==='saved'?'Saved accepted-audio capture':'Incomplete or pending capture'} — {c.outcome}</p>)}
      <ol>{review.turns.map(t=><li key={t.id}><strong>{t.role==='recruiter'?'Recruiter':'Candidate'}</strong> · {(t.start_ms/1000).toFixed(1)}–{(t.end_ms/1000).toFixed(1)}s: {t.text}</li>)}</ol>
      {review.next_offset!==null && <button disabled={busy} onClick={()=>void act(async()=>{setReview(await reviewTranscript(context,review.next_offset!));})}>Next transcript page</button>}</div>}
    {candidate && !privacyOnly && <p><a href="/transcript-privacy">Transcript privacy and deletion after the interview</a> — keep this browser's private cookie; no joining link or transcript is stored in the URL.</p>}
  </section>;
}
