import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, setLogLevel } from "livekit-client";
import type { RemoteTrack, RemoteTrackPublication } from "livekit-client";
import { interviewAccess } from "../api/livekitInterview";
import { syntheticInterviewMedia } from "./syntheticInterviewMedia";
import type { Interview } from "../api/interviews";

// SDK diagnostics can contain connection details; public UI uses fixed errors.
setLogLevel("silent");

export default function LiveInterviewPage({jobId,interview,onBack}:{jobId:string;interview:Interview;onBack:()=>void}) {
  const [slot,setSlot]=useState<"a"|"b">("a");const [confirmed,setConfirmed]=useState(false);
  const [synthetic,setSynthetic]=useState(true);const [state,setState]=useState("Not connected");
  const [joined,setJoined]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [muted,setMuted]=useState(false);const [cameraOff,setCameraOff]=useState(false);
  const [peers,setPeers]=useState(0);const [audioBlocked,setAudioBlocked]=useState(false);
  const [remoteMuted,setRemoteMuted]=useState(false);const [remoteCameraOff,setRemoteCameraOff]=useState(false);
  const local=useRef<HTMLDivElement>(null);const remote=useRef<HTMLDivElement>(null);
  const room=useRef<Room|null>(null);const generation=useRef(0);
  const media=useRef<ReturnType<typeof syntheticInterviewMedia>|null>(null);
  function stopMedia() {media.current?.dispose();media.current=null;local.current?.replaceChildren();remote.current?.replaceChildren();}
  async function leave() {generation.current++;const active=room.current;room.current=null;
    stopMedia();setJoined(false);setBusy(false);setPeers(0);setState("Left interview");try {await active?.disconnect(true);} catch {}}
  useEffect(()=>()=>{generation.current++;const active=room.current;room.current=null;stopMedia();void active?.disconnect(true).catch(()=>{});},[jobId,interview.id]);
  async function join() {
    if(!confirmed || busy || room.current)return;
    const current=++generation.current;setBusy(true);setError("");setState("Connecting…");
    const active=new Room();room.current=active;
    function remoteState(publication:RemoteTrackPublication) {
      if(current!==generation.current)return;
      if(publication.source===Track.Source.Camera)setRemoteCameraOff(publication.isMuted);
      if(publication.source===Track.Source.Microphone)setRemoteMuted(publication.isMuted);
    }
    function attach(track:RemoteTrack,publication:RemoteTrackPublication) {if(current!==generation.current)return;
      remoteState(publication);
      if(track.kind===Track.Kind.Video || track.kind===Track.Kind.Audio) {const element=track.attach();
        element.setAttribute("aria-label",track.kind===Track.Kind.Video?"Remote video":"Remote audio");remote.current?.appendChild(element);}}
    active.on(RoomEvent.TrackSubscribed,attach).on(RoomEvent.TrackUnsubscribed,track=>track.detach().forEach(e=>e.remove()))
      .on(RoomEvent.LocalTrackPublished,publication=>{if(publication.track?.kind===Track.Kind.Video && current===generation.current){
        const element=publication.track.attach();element.muted=true;element.setAttribute("aria-label","Local video");local.current?.appendChild(element);}})
      .on(RoomEvent.ParticipantConnected,()=>{if(current===generation.current)setPeers(active.remoteParticipants.size);})
      .on(RoomEvent.ParticipantDisconnected,()=>{if(current===generation.current)setPeers(active.remoteParticipants.size);})
      .on(RoomEvent.TrackMuted,(publication,participant)=>{if(!participant.isLocal)remoteState(publication as RemoteTrackPublication);})
      .on(RoomEvent.TrackUnmuted,(publication,participant)=>{if(!participant.isLocal)remoteState(publication as RemoteTrackPublication);})
      .on(RoomEvent.AudioPlaybackStatusChanged,()=>{if(current===generation.current)setAudioBlocked(!active.canPlaybackAudio);})
      .on(RoomEvent.Disconnected,()=>{if(room.current===active){room.current=null;generation.current++;stopMedia();setJoined(false);setBusy(false);setPeers(0);setState("Disconnected");setError("Interview connection ended. Check the network before joining again.");}});
    try {
      const generated=synthetic?syntheticInterviewMedia(slot):null;media.current=generated;
      let access=await interviewAccess(jobId,interview.id,slot);
      if(current!==generation.current)return;
      await active.connect(access.server_url,access.token);access={server_url:"",token:"",expires_in:300};
      if(current!==generation.current){await active.disconnect(true);return;}
      if(generated){await active.localParticipant.publishTrack(generated.video,{source:Track.Source.Camera});
        await active.localParticipant.publishTrack(generated.audio,{source:Track.Source.Microphone});}
      else await active.localParticipant.enableCameraAndMicrophone();
      if(current!==generation.current){await active.disconnect(true);return;}
      setJoined(true);setMuted(false);setCameraOff(false);setPeers(active.remoteParticipants.size);setState("Connected");
    } catch {if(current===generation.current){await leave();setError("Interview connection failed. Check configuration, network or media permissions before joining again.");}
      else {try {await active.disconnect(true);} catch {}}}
    finally {if(current===generation.current)setBusy(false);}
  }
  async function toggle(kind:"microphone"|"camera") {
    const active=room.current;if(!active || !joined || busy)return;const current=generation.current;setBusy(true);setError("");
    try {if(kind==="microphone"){await active.localParticipant.setMicrophoneEnabled(muted);if(current===generation.current)setMuted(!muted);}
      else {await active.localParticipant.setCameraEnabled(cameraOff);if(current===generation.current)setCameraOff(!cameraOff);}}
    catch {if(current===generation.current)setError("Media control failed. Leave the interview if privacy is uncertain.");}
    finally {if(current===generation.current)setBusy(false);}
  }
  return <main className="app-shell"><section className="card" aria-label="Synthetic interview proof">
    <h1>Interview audio/video proof</h1><p>Recruiter-controlled synthetic testing only. No recording, transcription or candidate access.</p>
    <p role="status">{state} · Remote participants: {peers}</p>
    {peers>0 && <p>Remote microphone: {remoteMuted?"muted":"active"} · Remote camera: {remoteCameraOff?"off":"on"}</p>}
    <fieldset disabled={busy || joined}><legend>Test session</legend>
      <label htmlFor="interview-slot">Browser slot</label><select id="interview-slot" value={slot} onChange={e=>setSlot(e.target.value as "a"|"b")}><option value="a">A</option><option value="b">B</option></select>
      <label><input type="checkbox" checked={synthetic} onChange={e=>setSynthetic(e.target.checked)} /> Use generated synthetic audio/video (no physical devices)</label>
      <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} /> I confirm this is a synthetic test in an isolated environment.</label>
    </fieldset><p className="helper-text">Use A and B in two browsers signed in as the owning recruiter. Device mode requires camera/microphone permission.</p>
    <button className="button button-primary" onClick={()=>void join()} disabled={!confirmed || busy || joined}>Join interview</button>
    <button className="button button-secondary" onClick={()=>void toggle("microphone")} disabled={!joined || busy}>{muted?"Unmute microphone":"Mute microphone"}</button>
    <button className="button button-secondary" onClick={()=>void toggle("camera")} disabled={!joined || busy}>{cameraOff?"Turn camera on":"Turn camera off"}</button>
    <button className="button button-secondary" onClick={()=>void leave()} disabled={!joined && !busy}>Leave interview</button>
    {audioBlocked && <button onClick={()=>void room.current?.startAudio().catch(()=>setError("Remote audio could not start."))}>Enable remote audio</button>}
    {error && <p role="alert" className="error-banner">{error}</p>}
    <div className="interview-media"><section><h2>Local video</h2><div ref={local} /></section><section><h2>Remote video/audio</h2><div ref={remote} /></section></div>
    <button className="button button-secondary" onClick={onBack}>Back to screening</button>
  </section></main>;
}
