import { LocalAudioTrack, LocalVideoTrack } from "livekit-client";

// Locally generated A/V for the Cloud proof, never office camera/microphone data.
export function syntheticInterviewMedia(slot:"a"|"b",speech?:AudioBuffer) {
  const canvas=document.createElement("canvas");canvas.width=480;canvas.height=270;
  const draw=canvas.getContext("2d")!;let frame=0;let stopped=false;
  function paint() {if(stopped)return;
    draw.fillStyle=slot==="a"?"#11665a":"#354991";draw.fillRect(0,0,480,270);
    draw.fillStyle="white";draw.font="26px sans-serif";draw.fillText(`SYNTHETIC TEST ${slot.toUpperCase()}`,70,100);
    draw.fillRect(40+(Date.now()/20)%380,180,40,20);frame=requestAnimationFrame(paint);}
  paint();const videoStream=canvas.captureStream(15);
  const context=new AudioContext();const oscillator=context.createOscillator();const gain=context.createGain();
  const destination=context.createMediaStreamDestination();gain.gain.value=0.005;oscillator.frequency.value=slot==="a"?220:330;
  if(!speech)oscillator.connect(gain);gain.connect(destination);oscillator.start();void context.resume().catch(()=>{});
  let spoken:AudioBufferSourceNode|null=null;
  function stopSpeech(){try{spoken?.stop();}catch{/* May not have started while resume was pending. */}spoken=null;}
  function play(){if(!speech||stopped)return;stopSpeech();const node=context.createBufferSource();spoken=node;node.buffer=speech;
    node.connect(destination);void context.resume().then(()=>{if(!stopped&&spoken===node)node.start();}).catch(()=>{});}
  const video=new LocalVideoTrack(videoStream.getVideoTracks()[0],undefined,true);
  const audio=new LocalAudioTrack(destination.stream.getAudioTracks()[0],undefined,true);
  return {video,audio,play,dispose:()=>{if(stopped)return;stopped=true;stopSpeech();cancelAnimationFrame(frame);
    video.stop();audio.stop();oscillator.stop();void context.close().catch(()=>{});}};
}
