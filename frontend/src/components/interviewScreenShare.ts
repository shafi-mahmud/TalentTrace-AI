import {Track} from 'livekit-client';
import type {LocalParticipant,LocalTrack} from 'livekit-client';
type Participant=Pick<LocalParticipant,'setScreenShareEnabled'|'getTrackPublication'|'unpublishTrack'>;
export interface SharingState {active:boolean;busy:boolean;error:string;}

// One controller per authorized room; no capture on construction or synchronization.
export class InterviewScreenShare {
 private closed=false;
 private busy=false;
 private ended:MediaStreamTrack|null=null;
 private onEnded=()=>this.sync();
 private participant:Participant;
 private changed:(value:SharingState)=>void;
 constructor(participant:Participant,changed:(value:SharingState)=>void){this.participant=participant;this.changed=changed;}
 private release(track?:LocalTrack){
  if(!track)return;
  track.stop();track.detach().forEach(element=>element.remove());
  void this.participant.unpublishTrack(track).catch(()=>{});
 }
 sync(error=''){
  if(this.closed)return;
  const track=this.participant.getTrackPublication(Track.Source.ScreenShare)?.track?.mediaStreamTrack??null;
  if(track!==this.ended){this.ended?.removeEventListener('ended',this.onEnded);this.ended=track;track?.addEventListener('ended',this.onEnded);}
  this.changed({active:!!track&&track.readyState==='live',busy:this.busy,error});
 }
 async toggle(){
  if(this.closed||this.busy)return;
  const active=this.participant.getTrackPublication(Track.Source.ScreenShare)?.track?.mediaStreamTrack.readyState==='live';
  this.busy=true;this.sync();
  try{
   // Native picker is reached only from the participant's explicit button action.
   const publication=await this.participant.setScreenShareEnabled(!active,{audio:false});
   if(this.closed){this.release(publication?.track);return;}
   this.busy=false;this.sync();
  }catch{
   this.release(this.participant.getTrackPublication(Track.Source.ScreenShare)?.track);
   this.busy=false;this.sync('Screen sharing was not started or stopped successfully. Check browser permissions.');
  }
 }
 close(){
  if(this.closed)return;
  this.closed=true;this.ended?.removeEventListener('ended',this.onEnded);this.ended=null;
  this.release(this.participant.getTrackPublication(Track.Source.ScreenShare)?.track);
 }
}
