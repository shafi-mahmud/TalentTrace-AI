import test from 'node:test';
import assert from 'node:assert/strict';
import {Track} from 'livekit-client';
import {readFileSync} from 'node:fs';
import {InterviewScreenShare} from '../src/components/interviewScreenShare.ts';

function harness(){
 const media=Object.assign(new EventTarget(),{readyState:'live'});
 let stops=0,unpublished=0,calls:any[]=[],publication:any;
 const values:any[]=[];
 const track={mediaStreamTrack:media,stop(){stops++;media.readyState='ended';},detach(){return [];}};
 let operation=async(enabled:boolean)=>{if(enabled){publication={track};return publication;}track.stop();publication=undefined;};
 const participant={getTrackPublication(source:any){assert.equal(source,Track.Source.ScreenShare);return publication;},
  async setScreenShareEnabled(enabled:boolean,options:any){calls.push([enabled,options]);return operation(enabled);},
  async unpublishTrack(t:any){assert.equal(t,track);unpublished++;publication=undefined;}};
 const controller=new InterviewScreenShare(participant as any,v=>values.push(v));
 return {controller,media,track,values,calls,setOperation(fn:any){operation=fn;},setPublication(){publication={track};},counts:()=>({stops,unpublished})};
}
test('sharing is explicit, screen-video-only and reflects actual SDK publication',async()=>{
 const x=harness();assert.equal(x.calls.length,0);x.controller.sync();assert.equal(x.values.at(-1).active,false);
 await x.controller.toggle();assert.deepEqual(x.calls,[[true,{audio:false}]]);assert.equal(x.values.at(-1).active,true);
 await x.controller.toggle();assert.equal(x.calls[1][0],false);assert.equal(x.values.at(-1).active,false);
 x.controller.close();
});
test('browser-native Stop clears active state without restarting capture',async()=>{
 const x=harness();await x.controller.toggle();
 x.media.readyState='ended';x.media.dispatchEvent(new Event('ended'));
 assert.equal(x.values.at(-1).active,false);assert.equal(x.calls.length,1);x.controller.close();
});
test('permission or publication denial is sanitized and does not claim sharing',async()=>{
 const x=harness();x.setOperation(async()=>{throw Error('PRIVATE permission data');});await x.controller.toggle();
 assert.equal(x.values.at(-1).active,false);assert.equal(x.values.at(-1).busy,false);
 assert.match(x.values.at(-1).error,/permissions/);assert.doesNotMatch(x.values.at(-1).error,/PRIVATE/);x.controller.close();
});
test('leave during screen picker stops and unpublishes late capture in its original room',async()=>{
 const x=harness();let resolve!:(v:any)=>void;
 x.setOperation(()=>new Promise(r=>{resolve=r;}));const start=x.controller.toggle();
 await x.controller.toggle();assert.equal(x.calls.length,1);
 x.controller.close();x.setPublication();resolve({track:x.track});await start;
 assert.equal(x.media.readyState,'ended');assert.equal(x.counts().unpublished,1);
 assert.ok(!x.values.some(v=>v.active));await x.controller.toggle();assert.equal(x.calls.length,1);
});
test('disconnect closes only screen publication and removes native-ended callbacks',async()=>{
 const x=harness();await x.controller.toggle();const before=x.values.length;x.controller.close();x.controller.close();
 x.media.dispatchEvent(new Event('ended'));assert.equal(x.values.length,before);
 assert.equal(x.counts().unpublished,1);assert.equal(x.media.readyState,'ended');
});
test('page routes screen video separately and leaves F4 microphone source unchanged',()=>{
 const source=readFileSync(new URL('../src/components/LiveInterviewPage.tsx',import.meta.url),'utf8');
 assert.match(source,/publication.source===Track.Source.ScreenShare&&track.kind===Track.Kind.Video/);
 assert.match(source,/remoteScreen.current\?\.appendChild\(element\)/);
 assert.match(source,/RoomEvent.LocalTrackUnpublished/);
 assert.match(source,/getTrackPublication\(Track.Source.Microphone\)\?\.track\?\.mediaStreamTrack/);
 assert.match(source,/disabled=\{!joined\|\|busy\|\|sharing.busy\|\|leaving.current\}/);
});
