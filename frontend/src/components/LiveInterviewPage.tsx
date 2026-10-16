import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, setLogLevel } from "livekit-client";
import type { RemoteTrack, RemoteTrackPublication } from "livekit-client";
import { interviewAccess, candidateAccess, candidateStatus, invitation, revokeInvitation, InterviewAccessError } from "../api/livekitInterview";
import { syntheticInterviewMedia } from "./syntheticInterviewMedia";
import type { Interview } from "../api/interviews";
import InterviewCaptions from "./InterviewCaptions";
import TranscriptPanel from "./TranscriptPanel";
import InterviewAnalysis from "./InterviewAnalysis";

// SDK diagnostics can contain connection details; public UI uses fixed errors.
setLogLevel("silent");

export default function LiveInterviewPage({jobId,interview,onBack,candidate=false}:{jobId?:string;interview?:Interview;onBack:()=>void;candidate?:boolean}) {
  const [confirmed,setConfirmed]=useState(false);
  const [invite,setInvite]=useState<{url:string;expires:string}|null>(null);const [inviteBusy,setInviteBusy]=useState(false);
  const [synthetic,setSynthetic]=useState(true);const [state,setState]=useState("Not connected");
  const [joined,setJoined]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [muted,setMuted]=useState(false);const [cameraOff,setCameraOff]=useState(false);
  const [peers,setPeers]=useState(0);const [audioBlocked,setAudioBlocked]=useState(false);
  const [remoteMuted,setRemoteMuted]=useState(false);const [remoteCameraOff,setRemoteCameraOff]=useState(false);
  const [storageAvailable,setStorageAvailable]=useState(false);
  const [syntheticSpeech,setSyntheticSpeech]=useState<AudioBuffer|undefined>();
  async function loadSynthetic(file?:File){if(!file)return;
    if(!/\.wav$/i.test(file.name)||file.size>2000000){setError('Choose a short generated synthetic WAV only.');return;}
    const decoder=new AudioContext();try{const buffer=await decoder.decodeAudioData(await file.arrayBuffer());
      if(buffer.duration>30)throw Error();setSyntheticSpeech(buffer);
    }catch{setError('Synthetic WAV could not be decoded.');}finally{void decoder.close();}}
  const local=useRef<HTMLDivElement>(null);const remote=useRef<HTMLDivElement>(null);
  const room=useRef<Room|null>(null);const generation=useRef(0);
  const captionFinalizer=useRef<(()=>Promise<void>)|null>(null);
  const leaving=useRef(false);
  const captionDraining=useRef(false);
  const media=useRef<ReturnType<typeof syntheticInterviewMedia>|null>(null);
  function stopMedia() {media.current?.dispose();media.current=null;local.current?.replaceChildren();remote.current?.replaceChildren();}
  async function leave(normal=false) {
    if(normal){if(leaving.current)return;leaving.current=true;setBusy(true);await captionFinalizer.current?.();}
    generation.current++;const active=room.current;room.current=null;
    stopMedia();setJoined(false);setBusy(false);setPeers(0);setState("Left interview");try {await active?.disconnect(true);} catch {}finally{leaving.current=false;}}
  useEffect(()=>()=>{generation.current++;const active=room.current;room.current=null;stopMedia();void active?.disconnect(true).catch(()=>{});},[jobId,interview?.id]);
  useEffect(()=>{if(!joined)return;let cancelled=false;const current=generation.current;const check=()=>{
    if(leaving.current || captionDraining.current)return;
    if(candidate)void candidateStatus().catch(()=>{if(!cancelled && current===generation.current){void leave();setError("Interview access ended or was revoked.");}});
    else if(interview && Date.now()>=Date.parse(interview.scheduled_at)+(interview.duration_minutes+15)*60000)void leave();
  };const timer=window.setInterval(check,15000);return()=>{cancelled=true;window.clearInterval(timer);};},[joined,candidate,interview]);
  async function createInvite() {if(!jobId || !interview || inviteBusy)return;setInviteBusy(true);setError("");setInvite(null);
    try {const value=await invitation(jobId,interview.id);setInvite({url:`${window.location.origin}/interview-join#invite=${value.token}`,expires:value.expires_at});}
    catch {setError("Invitation was not confirmed. Review interview status before trying again.");}finally{setInviteBusy(false);}}
  async function revoke() {if(!jobId || !interview || inviteBusy)return;setInviteBusy(true);setInvite(null);setError("");
    try{await revokeInvitation(jobId,interview.id);}catch{setError("Revocation or live disconnection was not confirmed. Retry revocation before sharing a replacement.");}finally{setInviteBusy(false);}}
  async function join() {
    if(!confirmed || busy || room.current)return;
    const current=++generation.current;setBusy(true);setError("");setState("Connecting…");
    let establishing=true;let stage='synthetic_media';
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
      .on(RoomEvent.Disconnected,()=>{if(!establishing&&room.current===active){room.current=null;generation.current++;stopMedia();setJoined(false);setBusy(false);setPeers(0);setState("Disconnected");setError("Interview connection ended. Check the network before joining again.");}});
    try {
      const generated=synthetic?syntheticInterviewMedia(candidate?"b":"a",syntheticSpeech):null;media.current=generated;
      stage='room_authorization';
      let access=candidate?await candidateAccess():await interviewAccess(jobId!,interview!.id);
      if(current!==generation.current)return;
      stage='livekit_connection';await active.connect(access.server_url,access.token);access={server_url:"",token:"",expires_in:300};
      if(current!==generation.current){await active.disconnect(true);return;}
      stage='media_publication';if(generated){await active.localParticipant.publishTrack(generated.video,{source:Track.Source.Camera});
        await active.localParticipant.publishTrack(generated.audio,{source:Track.Source.Microphone});}
      else await active.localParticipant.enableCameraAndMicrophone();
      if(current!==generation.current){await active.disconnect(true);return;}
      establishing=false;setJoined(true);setMuted(false);setCameraOff(false);setPeers(active.remoteParticipants.size);setState("Connected");
    } catch(failure) {if(current===generation.current){await leave();
        const code=failure&&typeof failure==='object'&&'reasonName' in failure?failure.reasonName:failure instanceof Error?failure.name:'';
        const safe=['NotAllowed','ServerUnreachable','InternalError','Cancelled','LeaveRequest','Timeout','WebSocket','ServiceNotFound','NotSupportedError','NotAllowedError','TypeError','ReferenceError'].includes(String(code))?String(code):'unavailable';
        setError(failure instanceof InterviewAccessError?failure.message:`Interview connection failed at ${stage} (${safe}). Check configuration, network or media permissions before joining again.`);}
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
    <h1>{candidate?"Candidate interview":"Recruiter interview"}</h1><p>Synthetic development testing only. No audio/video recording. Optional text storage has separate consent controls below.</p>
    {!candidate && <section aria-label="Candidate invitation"><h2>Candidate invitation</h2><p>One-use link. Treat it as a secret. Join window: 10 minutes before until 15 minutes after the interview.</p>
      <button disabled={inviteBusy} onClick={()=>void createInvite()}>Generate replacement invitation</button>
      <button disabled={inviteBusy} onClick={()=>void revoke()}>Revoke candidate access</button>
      {invite && <><p>Expires: {new Date(invite.expires).toLocaleString()}</p><button onClick={()=>void navigator.clipboard.writeText(invite.url).catch(()=>setError("Clipboard unavailable. Generate and copy in a supported browser."))}>Copy invitation link</button><p>Only the newly generated link can be copied. Previous links are invalidated.</p></>}
    </section>}
    <p role="status">{state} · Remote participants: {peers}</p>
    {peers>0 && <p>Remote microphone: {remoteMuted?"muted":"active"} · Remote camera: {remoteCameraOff?"off":"on"}</p>}
    <fieldset disabled={busy || joined}><legend>Test session</legend>
      <label><input type="checkbox" checked={synthetic} onChange={e=>setSynthetic(e.target.checked)} /> Use generated synthetic audio/video (no physical devices)</label>
      <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} /> I confirm this is a synthetic test in an isolated environment.</label>
    </fieldset><p className="helper-text">Recruiter signs in; candidate uses the invitation in a separate browser session. Device mode requires camera/microphone permission and headphones.</p>
    <button className="button button-primary" onClick={()=>void join()} disabled={!confirmed || busy || joined}>Join interview</button>
    <button className="button button-secondary" onClick={()=>void toggle("microphone")} disabled={!joined || busy}>{muted?"Unmute microphone":"Mute microphone"}</button>
    <button className="button button-secondary" onClick={()=>void toggle("camera")} disabled={!joined || busy}>{cameraOff?"Turn camera on":"Turn camera off"}</button>
    <button className="button button-secondary" onClick={()=>void leave(true)} disabled={(!joined && !busy) || leaving.current}>Leave interview</button>
    {audioBlocked && <button onClick={()=>void room.current?.startAudio().catch(()=>setError("Remote audio could not start."))}>Enable remote audio</button>}
    {error && <p role="alert" className="error-banner">{error}</p>}
    <TranscriptPanel key={`${candidate?'candidate':jobId}:${interview?.id??'current'}`} candidate={candidate} jobId={jobId} interviewId={interview?.id} connected={joined} onAvailability={setStorageAvailable}/>
    {import.meta.env.DEV&&synthetic&&<section aria-label="Synthetic speech rehearsal"><p>Development-only generated speech; no physical microphone. Select before joining; play only after both caption consents. WAV stays in browser memory.</p>
      <label>Generated synthetic speech WAV<input type="file" accept=".wav" disabled={joined} onChange={e=>void loadSynthetic(e.target.files?.[0])}/></label>
      <button disabled={!joined||!syntheticSpeech} onClick={()=>media.current?.play()}>Play generated synthetic speech</button></section>}
    {!candidate && jobId && interview && <InterviewAnalysis key={`analysis:${interview.id}`} jobId={jobId} interviewId={interview.id} revision={interview.criteria_revision}/>}
    <InterviewCaptions onFinalizing={active=>{captionDraining.current=active;}} storageAvailable={storageAvailable} connected={joined} candidate={candidate} jobId={jobId} interviewId={interview?.id} microphoneMuted={muted} finalizerRef={captionFinalizer}
      microphone={()=>room.current?.localParticipant.getTrackPublication(Track.Source.Microphone)?.track?.mediaStreamTrack ?? null}/>
    <div className="interview-media"><section><h2>Local video</h2><div ref={local} /></section><section><h2>Remote video/audio</h2><div ref={remote} /></section></div>
    <button className="button button-secondary" onClick={onBack}>Back to screening</button>
  </section></main>;
}
