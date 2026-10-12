import {useEffect,useRef,useState} from "react";
import {captionUrl,isCaption} from "../api/captions";
import type {Caption} from "../api/captions";

export default function InterviewCaptions({connected,candidate,jobId,interviewId,microphone}:{
  connected:boolean;candidate:boolean;jobId?:string;interviewId?:string;microphone:()=>MediaStreamTrack|null;
}) {
  const [agreed,setAgreed]=useState(false);const [state,setState]=useState("Off");const [rows,setRows]=useState<Caption[]>([]);
  const socket=useRef<WebSocket|null>(null);const context=useRef<AudioContext|null>(null);
  const generation=useRef(0);const heartbeat=useRef<ReturnType<typeof setInterval>|null>(null);
  const connectionTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  function stop() {
    generation.current++;if(heartbeat.current)clearInterval(heartbeat.current);heartbeat.current=null;
    if(connectionTimer.current)clearTimeout(connectionTimer.current);connectionTimer.current=null;
    const audio=context.current;context.current=null;void audio?.close().catch(()=>{});
    const old=socket.current;socket.current=null;
    if(old?.readyState===WebSocket.OPEN)old.send("stop");old?.close();
    setAgreed(false);setRows([]);setState("Stopped");
  }
  useEffect(()=>()=>{stop();},[connected,candidate,jobId,interviewId]);
  async function startAudio(current:number,ws:WebSocket) {
    const track=microphone();if(!track || track.readyState!=="live")throw Error();
    const audio=new AudioContext({sampleRate:16000});context.current=audio;
    await audio.audioWorklet.addModule(new URL("./captionAudio.js",import.meta.url));
    if(current!==generation.current){await audio.close();return;}
    if(audio.sampleRate!==16000)throw Error();
    const source=audio.createMediaStreamSource(new MediaStream([track]));
    const worklet=new AudioWorkletNode(audio,"caption-audio");const silent=audio.createGain();silent.gain.value=0;
    source.connect(worklet);worklet.connect(silent);silent.connect(audio.destination);
    worklet.port.onmessage=e=>{
      if(current!==generation.current || ws.readyState!==WebSocket.OPEN)return;
      if(ws.bufferedAmount>64000){stop();return;}
      ws.send(e.data);
    };
    await audio.resume();
  }
  function consent() {
    if(!connected || !agreed || socket.current)return;
    const current=++generation.current;setRows([]);setState("Connecting captions…");
    const ws=new WebSocket(captionUrl(candidate,jobId,interviewId));socket.current=ws;
    connectionTimer.current=setTimeout(()=>{if(current===generation.current){stop();setState("Caption connection was not confirmed. Video continues.");}},5000);
    ws.onopen=()=>{if(current!==generation.current)return;ws.send("consent");heartbeat.current=setInterval(()=>{if(ws.readyState===WebSocket.OPEN)ws.send("ping");},1000);};
    ws.onmessage=e=>{
      if(current!==generation.current)return;
      if(connectionTimer.current)clearTimeout(connectionTimer.current);connectionTimer.current=null;
      let value;try{value=JSON.parse(e.data);}catch{stop();return;}
      if(value?.kind==="active"){setState("Live — local CPU captions, maximum two minutes");void startAudio(current,ws).catch(()=>{stop();setState("Captions unavailable. Video continues.");});}
      else if(value?.kind==="stopped"){stop();}
      else if(value?.kind==="waiting"){setState("Waiting for both participants");}
      else if(isCaption(value)){setRows(old=>old.some(c=>c.sequence===value.sequence)?old:[...old.slice(-29),value]);}
      else {stop();}
    };
    ws.onclose=()=>{if(current===generation.current){stop();setState("Captions unavailable or stopped. Video continues.");}};
    ws.onerror=()=>{if(current===generation.current){stop();setState("Captions unavailable. Video continues.");}};
  }
  return <section aria-label="Temporary interview captions"><h2>Free local captions</h2>
    <p>Optional English captions processed on this computer. Both participants must consent. No recording or saved transcript; stop clears captions.</p>
    <label><input type="checkbox" checked={agreed} disabled={!connected || !!socket.current} onChange={e=>setAgreed(e.target.checked)}/> I consent to temporary processing of my microphone audio for this two-minute synthetic test.</label>
    <button disabled={!connected || !agreed || !!socket.current} onClick={consent}>Consent to captions</button>
    <button disabled={!socket.current} onClick={stop}>Withdraw consent / stop captions</button>
    <p role="status">{state}</p><ul aria-label="Live captions">{rows.map(c=><li key={c.sequence}>{c.role==="recruiter"?"Recruiter":"Candidate"} · {c.start.toFixed(1)}–{c.end.toFixed(1)}s: {c.text}</li>)}</ul>
  </section>;
}
