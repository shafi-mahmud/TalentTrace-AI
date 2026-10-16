import {useEffect,useRef,useState} from "react";
import {captionUrl,isCaption,isFinalization} from "../api/captions";
import type {Caption} from "../api/captions";

export default function InterviewCaptions({connected,candidate,jobId,interviewId,microphone,microphoneMuted=false,finalizerRef,storageAvailable=false}:{
  connected:boolean;candidate:boolean;jobId?:string;interviewId?:string;microphone:()=>MediaStreamTrack|null;microphoneMuted?:boolean;
  storageAvailable?:boolean;
  finalizerRef?:{current:(()=>Promise<void>)|null};
}) {
  const [agreed,setAgreed]=useState(false);const [state,setState]=useState("Off");const [rows,setRows]=useState<Caption[]>([]);
  const socket=useRef<WebSocket|null>(null);const context=useRef<AudioContext|null>(null);
  const generation=useRef(0);const heartbeat=useRef<ReturnType<typeof setInterval>|null>(null);
  const connectionTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const audioCleanup=useRef<(()=>void)|null>(null);
  const muted=useRef(microphoneMuted);muted.current=microphoneMuted;
  const duration=useRef(120);
  const workletRef=useRef<AudioWorkletNode|null>(null);const trackRef=useRef<MediaStreamTrack|null>(null);
  const finishing=useRef(false);const endSent=useRef(false);const acknowledged=useRef(false);
  const forwarded=useRef({frames:0,samples:0});const captured=useRef(0);
  const finishPromise=useRef<Promise<void>|null>(null);const finishResolve=useRef<(()=>void)|null>(null);
  const finishTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const flushTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const terminalStatus=useRef<string|null>(null);
  const [storageStatus,setStorageStatus]=useState("");
  function closeAudio() {
    audioCleanup.current?.();audioCleanup.current=null;
    workletRef.current=null;trackRef.current=null;
    const audio=context.current;context.current=null;void audio?.close().catch(()=>{});
  }
  function stop() {
    generation.current++;if(heartbeat.current)clearInterval(heartbeat.current);heartbeat.current=null;
    if(connectionTimer.current)clearTimeout(connectionTimer.current);connectionTimer.current=null;
    if(finishTimer.current)clearTimeout(finishTimer.current);finishTimer.current=null;
    if(flushTimer.current)clearTimeout(flushTimer.current);flushTimer.current=null;
    closeAudio();
    const old=socket.current;socket.current=null;
    try{if(old?.readyState===WebSocket.OPEN)old.send("stop");}catch{/* Connection already lost. */}old?.close();
    finishing.current=false;finishResolve.current?.();finishResolve.current=null;finishPromise.current=null;
    setAgreed(false);setRows([]);setState("Captions stopped. Microphone/video may remain active for the interview.");
  }
  useEffect(()=>()=>{stop();},[connected,candidate,jobId,interviewId]);
  if(finalizerRef)finalizerRef.current=finish;
  useEffect(()=>{workletRef.current?.port.postMessage({kind:"mute",value:microphoneMuted || !trackRef.current?.enabled || !!trackRef.current?.muted});},[microphoneMuted]);
  function finish():Promise<void> {
    if(!socket.current)return Promise.resolve();
    if(finishPromise.current)return finishPromise.current;
    finishPromise.current=new Promise<void>(resolve=>{finishResolve.current=resolve;});
    if(!finishing.current){
      finishTimer.current=setTimeout(()=>{stop();setState("Finalization unconfirmed — accepted audio may be incomplete. No retry was sent.");},40000);
      if(socket.current.readyState===WebSocket.OPEN){
        try{socket.current.send("finish");}catch{stop();setState("Finalization unavailable — connection ended.");return Promise.resolve();}
      }else {stop();setState("Finalization unavailable — connection not established.");return Promise.resolve();}
    }
    return finishPromise.current;
  }
  function sendEnd(ws:WebSocket) {
    if(endSent.current || ws.readyState!==WebSocket.OPEN)return;
    endSent.current=true;
    try{ws.send(JSON.stringify({kind:"end",...forwarded.current,captured_samples:captured.current}));}
    catch{stop();setState("Audio end unconfirmed — connection ended.");return;}
    closeAudio();
  }
  function freeze(ws:WebSocket) {
    if(finishing.current)return;
    finishing.current=true;setState("Finishing accepted audio…");
    if(!finishTimer.current)finishTimer.current=setTimeout(()=>{stop();setState("Finalization unconfirmed — no automatic retry.");},40000);
    if(workletRef.current){
      flushTimer.current=setTimeout(()=>{stop();setState("Audio flush failed — finalization incomplete.");},2000);
      workletRef.current.port.postMessage({kind:"flush"});
    }else {sendEnd(ws);}
  }
  async function startAudio(current:number,ws:WebSocket) {
    const track=microphone();if(!track || track.readyState!=="live")throw Error();trackRef.current=track;
    const audio=new AudioContext({sampleRate:16000});context.current=audio;
    const captureEnded=()=>{
      if(current!==generation.current || context.current!==audio)return;
      if(audio.state==="closed" || track.readyState==="ended"){
        stop();setState("Caption audio capture ended. Video continues independently.");
      }
    };
    audio.addEventListener("statechange",captureEnded);track.addEventListener("ended",captureEnded);
    const syncMute=()=>workletRef.current?.port.postMessage({kind:"mute",value:muted.current || !track.enabled || track.muted});
    track.addEventListener("mute",syncMute);track.addEventListener("unmute",syncMute);
    audioCleanup.current=()=>{audio.removeEventListener("statechange",captureEnded);track.removeEventListener("ended",captureEnded);track.removeEventListener("mute",syncMute);track.removeEventListener("unmute",syncMute);};
    await audio.audioWorklet.addModule(new URL("./captionAudio.js",import.meta.url));
    if(current!==generation.current || finishing.current){await audio.close();return;}
    if(audio.sampleRate!==16000)throw Error();
    const source=audio.createMediaStreamSource(new MediaStream([track]));
    const worklet=new AudioWorkletNode(audio,"caption-audio");const silent=audio.createGain();silent.gain.value=0;
    workletRef.current=worklet;
    source.connect(worklet);worklet.connect(silent);silent.connect(audio.destination);
    worklet.port.onmessage=e=>{
      if(current!==generation.current || ws.readyState!==WebSocket.OPEN)return;
      if(e.data?.kind==="flushed"){
        if(!finishing.current || endSent.current || !Number.isInteger(e.data.captured_samples)
          || e.data.captured_samples<forwarded.current.samples || e.data.captured_samples>duration.current*16000){stop();return;}
        captured.current=e.data.captured_samples;
        if(flushTimer.current)clearTimeout(flushTimer.current);flushTimer.current=null;
        sendEnd(ws);return;
      }
      if(endSent.current || !Number.isInteger(e.data?.byteLength) || e.data.byteLength<2 || e.data.byteLength>3200 || e.data.byteLength%2){stop();return;}
      // The interview mute applies to the separate STT path too. Do not forward
      // muted frames; keep heartbeat/consent active for the other participant.
      if(muted.current || !track.enabled || track.muted)return;
      if(ws.bufferedAmount>64000){stop();return;}
      try{ws.send(e.data);}catch{stop();setState("Audio delivery interrupted.");return;}
      forwarded.current.frames++;forwarded.current.samples+=e.data.byteLength/2;
    };
    syncMute();
    await audio.resume();
    if(current===generation.current && audio.state!=="running")throw Error();
  }
  function consent() {
    if(!connected || !agreed || socket.current)return;
    const current=++generation.current;setRows([]);setState("Connecting captions…");
    duration.current=120;
    forwarded.current={frames:0,samples:0};captured.current=0;endSent.current=false;acknowledged.current=false;finishing.current=false;terminalStatus.current=null;
    const ws=new WebSocket(captionUrl(candidate,jobId,interviewId));socket.current=ws;
    connectionTimer.current=setTimeout(()=>{if(current===generation.current){stop();setState("Caption connection was not confirmed. Video continues.");}},5000);
    ws.onopen=()=>{if(current!==generation.current)return;ws.send("consent");heartbeat.current=setInterval(()=>{if(ws.readyState===WebSocket.OPEN)ws.send("ping");},1000);};
    ws.onmessage=e=>{
      if(current!==generation.current)return;
      if(connectionTimer.current)clearTimeout(connectionTimer.current);connectionTimer.current=null;
      let value;try{value=JSON.parse(e.data);}catch{stop();return;}
      if(value?.kind==="active"){
        const limit=value.duration_seconds ?? 120;
        if(!Number.isInteger(limit) || limit<120 || limit>300){stop();return;}
        duration.current=limit;
        setState("Starting caption audio capture…");
        void startAudio(current,ws).then(()=>{
          if(current===generation.current && context.current?.state==="running")setState(`Live — local CPU captions, maximum ${duration.current===120?"two minutes":`${duration.current} seconds (isolated test)`}`);
        }).catch(()=>{
          if(current===generation.current){stop();setState("Captions unavailable. Video continues.");}
        });
      }
      else if(value?.kind==="stopped"){
        const status=terminalStatus.current;stop();if(status)setState(status);
      }
      else if(value?.kind==="finishing"){
        if(Object.keys(value).length!==2 || value.deadline_seconds!==35){stop();return;}
        freeze(ws);
      }
      else if(value?.kind==="accepted"){
        if(!endSent.current || Object.keys(value).length!==3 || value.frames!==forwarded.current.frames || value.samples!==forwarded.current.samples){stop();return;}
        acknowledged.current=true;
      }
      else if(value?.kind==="storage"){
        if(Object.keys(value).length!==3 || !["disabled","saved","incomplete","unconfirmed"].includes(value.status) || !Number.isInteger(value.committed_turns) || value.committed_turns<0 || value.committed_turns>150){stop();return;}
        setStorageStatus(`Transcript storage: ${value.status}; acknowledged turns: ${value.committed_turns}.`);
      }
      else if(isFinalization(value,duration.current)){
        const own=value.roles[candidate?"candidate":"recruiter"];
        const valid=value.outcome!=="drained" || (acknowledged.current && own.accepted_frames===forwarded.current.frames && own.accepted_samples===forwarded.current.samples && own.captured_samples===captured.current);
        if(!valid){stop();setState("Finalization unconfirmed — acknowledgement mismatch.");return;}
        terminalStatus.current=`Finalization: ${value.outcome}. Browser-observed samples: ${own.captured_samples ?? "unconfirmed"}; forwarded: ${forwarded.current.samples}; backend accepted: ${own.accepted_samples}; STT processed: ${own.processed_samples}; caption events: ${own.caption_events}. Accepted audio only — full-interview completeness is not established.`;
      }
      else if(value?.kind==="waiting"){setState("Waiting for both participants");}
      else if(isCaption(value,duration.current)){setRows(old=>old.some(c=>c.sequence===value.sequence)?old:[...old.slice(-29),value]);}
      else {stop();}
    };
    ws.onclose=()=>{if(current===generation.current){stop();setState("Captions unavailable or stopped. Video continues.");}};
    ws.onerror=()=>{if(current===generation.current){stop();setState("Captions unavailable. Video continues.");}};
  }
  return <section aria-label="Temporary interview captions"><h2>Free local captions</h2>
    <p>{storageAvailable ? "Optional English captions processed on this computer. Both participants must consent to captions. No audio/video recording. Temporary captions clear on stop; optional transcript storage requires separate consent." : "Optional English captions processed on this computer. Both participants must consent. No recording or saved transcript; stop clears captions."}</p>
    {storageStatus && <p role="status">{storageStatus}</p>}
    <label><input type="checkbox" checked={agreed} disabled={!connected || !!socket.current} onChange={e=>setAgreed(e.target.checked)}/> I consent to temporary microphone processing for this synthetic test: two minutes by default, up to five minutes only in an isolated extended test.</label>
    <button disabled={!connected || !agreed || !!socket.current} onClick={consent}>Consent to captions</button>
    <button disabled={!socket.current} onClick={stop}>Withdraw consent / stop captions</button>
    <button disabled={!socket.current || finishing.current} onClick={()=>void finish()}>Finish captions normally</button>
    <p role="status">{microphoneMuted && state.startsWith("Live") ? "Your microphone is muted; your caption audio is paused." : state}</p><ul aria-label="Live captions">{rows.map(c=><li key={c.sequence}>{c.role==="recruiter"?"Recruiter":"Candidate"} · {c.start.toFixed(1)}–{c.end.toFixed(1)}s: {c.text}</li>)}</ul>
  </section>;
}
