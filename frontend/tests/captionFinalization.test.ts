import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";
import {isFinalization} from "../src/api/captions.ts";

test("worklet conserves complete and sub-100-ms residual samples exactly once",()=>{
  let Processor:any;const messages:any[]=[];
  class Base{port:any={onmessage:null,postMessage(v:any){messages.push(v);}};}
  runInNewContext(readFileSync(new URL("../src/components/captionAudio.js",import.meta.url),"utf8"),{
    AudioWorkletProcessor:Base,registerProcessor:(_name:string,value:any)=>{Processor=value;}});
  const p=new Processor();p.port.onmessage({data:{kind:"mute",value:false}});
  const input=Float32Array.from({length:1637},(_,i)=>(i%200-100)/200);
  p.process([[input]]);assert.equal(messages.length,1);assert.equal(messages[0].byteLength,3200);
  p.port.onmessage({data:{kind:"flush"}});
  assert.equal(messages[1].byteLength,74);
  const pcm=[...new Int16Array(messages[0]),...new Int16Array(messages[1])];
  assert.deepEqual(pcm,Array.from(input,x=>Math.round(x*32767)));
  assert.equal(messages[2].kind,"flushed");assert.equal(messages[2].captured_samples,1637);
  p.port.onmessage({data:{kind:"flush"}});p.process([[input]]);
  assert.equal(messages.length,3);assert.equal(p.index,0);assert.ok(p.samples.every((n:number)=>n===0));
});

test("muting discards residual audio and never flushes muted speech",()=>{
  let Processor:any;const messages:any[]=[];
  class Base{port:any={onmessage:null,postMessage(v:any){messages.push(v);}};}
  runInNewContext(readFileSync(new URL("../src/components/captionAudio.js",import.meta.url),"utf8"),{
    AudioWorkletProcessor:Base,registerProcessor:(_name:string,value:any)=>{Processor=value;}});
  const p=new Processor();p.port.onmessage({data:{kind:"mute",value:false}});
  p.process([[new Float32Array(100).fill(.5)]]);
  p.port.onmessage({data:{kind:"mute",value:true}});p.process([[new Float32Array(100).fill(.8)]]);
  p.port.onmessage({data:{kind:"flush"}});
  assert.equal(messages.length,1);assert.equal(messages[0].kind,"flushed");assert.equal(messages[0].captured_samples,200);
});

test("finalization accounting rejects malformed, excessive and misleading success",()=>{
  const c={accepted_frames:1,accepted_samples:50,processed_samples:50,caption_events:1,captured_samples:50};
  const value={kind:"finalized",outcome:"drained",roles:{candidate:c,recruiter:c}};
  assert.ok(isFinalization(value));
  for(const patch of [{processed_samples:51},{captured_samples:null},{accepted_samples:5e6},{accepted_frames:-1},{caption_events:999},{token:"secret"}])
    assert.equal(isFinalization({...value,roles:{candidate:{...c,...patch},recruiter:c}}),false);
  assert.equal(isFinalization({...value,outcome:"success"}),false);
  assert.equal(isFinalization({...value,roles:{candidate:c,admin:c}}),false);
});
