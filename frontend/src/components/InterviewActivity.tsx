import {useEffect,useRef,useState} from 'react';
import * as api from '../api/interviewAttention';
import {observeActivity} from './interviewActivityObserver';
export default function InterviewActivity({candidate,connected,jobId,interviewId}:{candidate:boolean;connected:boolean;jobId?:string;interviewId?:string}){
 const [checked,setChecked]=useState(false),[sharing,setSharing]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [value,setValue]=useState<api.Activity|null>(null);const [fullscreen,setFullscreen]=useState(false);
 const scope=useRef(0),run=useRef<string|null>(null),stop=useRef<(()=>void)|null>(null);
 function clear(reportFailure=false){scope.current++;stop.current?.();stop.current=null;const id=run.current;run.current=null;if(id)void api.withdraw(id).catch(()=>{if(reportFailure)setError("Stopped locally; last status expires within 30 seconds.");});setSharing(false);setChecked(false);}
 useEffect(()=>{setError('');setValue(null);return ()=>clear();},[candidate,connected,jobId,interviewId]);
 useEffect(()=>{
  if(candidate||!connected||!jobId||!interviewId)return;
  let active=true,pending=false;
  const refresh=async()=>{if(pending)return;pending=true;try{const v=await api.status(jobId,interviewId);if(active){setValue(v);setError('');}}catch{if(active){setValue(null);setError('Status unavailable.');}}finally{pending=false;}};
  void refresh();const timer=setInterval(()=>void refresh(),5000);return()=>{active=false;clearInterval(timer);};
 },[candidate,connected,jobId,interviewId]);
 useEffect(()=>{const change=()=>setFullscreen(!!document.fullscreenElement);document.addEventListener('fullscreenchange',change);return()=>document.removeEventListener('fullscreenchange',change);},[]);
 async function enable(){
  if(!candidate||!connected||!checked||busy||sharing)return;
  const ticket=scope.current;setBusy(true);setError('');
  try{const id=await api.consent();if(ticket!==scope.current){void api.withdraw(id).catch(()=>{});return;}run.current=id;setSharing(true);
   stop.current=observeActivity(document,v=>api.send(id,v),()=>{clear();setError('Stopped locally; last status expires within 30 seconds.');});
  }catch{if(ticket===scope.current)setError('Status sharing unavailable.');}finally{setBusy(false);}
 }
 async function toggleFullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{setError('Fullscreen unavailable.');}}
 const supported=typeof document!=="undefined"&&document.fullscreenEnabled;
 return <section className="card" aria-label="Optional interview activity"><h2>Optional activity status</h2>
  <p>Tab visibility and fullscreen status are not proof of attention, identity or cheating.</p>
  {candidate?<><label><input type="checkbox" checked={checked} disabled={!connected||sharing||busy} onChange={e=>setChecked(e.target.checked)}/> Share this tab’s visibility and fullscreen status with the recruiter.</label>
   <button disabled={!connected||busy||!checked||sharing} onClick={()=>void enable()}>Share status</button>
   <button disabled={!sharing} onClick={()=>clear(true)}>Stop sharing status</button>
   <button disabled={!connected||!supported} onClick={()=>void toggleFullscreen()}>{!supported?'Fullscreen unavailable':fullscreen?'Exit fullscreen':'Enter fullscreen'}</button>
   <p role="status">{sharing?'Status sharing on':'Local status sharing off'}</p></>:<p role="status">{!connected?'Join interview to view status.':value?`Last reported tab: ${value.visibility} · Page fullscreen: ${value.fullscreen}`:'Not shared or unavailable.'}</p>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
