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
