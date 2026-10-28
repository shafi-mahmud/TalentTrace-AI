import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';

test('generated speech uses a synthetic publication track and late resume cannot restart disposed audio',async()=>{
  const sources:any[]=[];let oscillatorConnections=0,stops=0,release=()=>{};
  const pending=new Promise<void>(r=>{release=r;});
  class Context{
    createOscillator(){return {frequency:{value:0},connect(){oscillatorConnections++;},start(){},stop(){}};}
    createGain(){return {gain:{value:0},connect(){}};}
    createMediaStreamDestination(){return {stream:{getAudioTracks:()=>['synthetic-audio']}};}
    createBufferSource(){const n={buffer:null,started:0,connect(){},start(){n.started++;},stop(){}};sources.push(n);return n;}
    resume(){return pending;}close(){return Promise.resolve();}
  }
  class Track{source:any;constructor(source:any){this.source=source;}stop(){stops++;}}
  const exports:any={};
  const source=ts.transpileModule(readFileSync(new URL('../src/components/syntheticInterviewMedia.ts',import.meta.url),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  runInNewContext(source,{exports,require:()=>({LocalAudioTrack:Track,LocalVideoTrack:Track}),AudioContext:Context,
    document:{createElement:()=>({getContext:()=>({fillRect(){},fillText(){}}),captureStream:()=>({getVideoTracks:()=>['synthetic-video']})})},
    requestAnimationFrame:()=>1,cancelAnimationFrame(){}});
  const media=exports.syntheticInterviewMedia('a',{duration:3});
  assert.equal(media.audio.source,'synthetic-audio');assert.equal(oscillatorConnections,0);
  media.play();media.play();media.dispose();media.dispose();release();await Promise.resolve();await Promise.resolve();
  assert.ok(sources.every(s=>s.started===0));assert.equal(stops,2);
});

test('approved WAV buffer feeds only the published synthetic microphone destination',async()=>{
 const fixture=readFileSync(new URL('../../backend/app/integrations/stt/synthetic/recruiter.wav',import.meta.url));
 assert.equal(fixture.toString('ascii',0,4),'RIFF');assert.equal(fixture.toString('ascii',8,12),'WAVE');
 const destination={stream:{getAudioTracks:()=>['generated-microphone']}};
 const speech={duration:3};let source:any,oscillatorConnected=false,closed=false;
 class Context{
  createOscillator(){return {frequency:{value:0},connect(){oscillatorConnected=true;},start(){},stop(){}};}
  createGain(){return {gain:{value:0},connect(){}};}
  createMediaStreamDestination(){return destination;}
  createBufferSource(){source={buffer:null,destination:null,starts:0,connect(d:any){source.destination=d;},start(){source.starts++;},stop(){}};return source;}
  async resume(){}async close(){closed=true;}
 }
 class Track{source:any;constructor(source:any){this.source=source;}stop(){}}
 const exports:any={};const code=ts.transpileModule(readFileSync(new URL('../src/components/syntheticInterviewMedia.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 runInNewContext(code,{exports,require:()=>({LocalAudioTrack:Track,LocalVideoTrack:Track}),AudioContext:Context,
  document:{createElement:()=>({getContext:()=>({fillRect(){},fillText(){}}),captureStream:()=>({getVideoTracks:()=>['generated-camera']})})},requestAnimationFrame:()=>1,cancelAnimationFrame(){}});
 const media=exports.syntheticInterviewMedia('a',speech);assert.equal(media.audio.source,'generated-microphone');
 media.play();await Promise.resolve();await Promise.resolve();
 assert.equal(source.buffer,speech);assert.equal(source.destination,destination);assert.equal(source.starts,1);
 assert.equal(oscillatorConnected,false);media.dispose();assert.equal(closed,true);
});
