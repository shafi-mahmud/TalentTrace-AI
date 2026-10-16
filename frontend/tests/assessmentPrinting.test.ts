import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {printAssessment} from '../src/api/assessmentPrinting.ts';
import type {PrintHost} from '../src/api/assessmentPrinting';
import type {ConsolidatedReport} from '../src/api/consolidatedAssessment';
const now=Date.parse('2026-10-17T12:00:00Z');
const cvOnly={interview:{state:'not_scheduled'}} as ConsolidatedReport;
function host(){
 const calls:string[]=[];let after=()=>{},before=()=>{},expire=()=>{};let ttl=0;
 const h:PrintHost={now:()=>now,mount:(_report,time)=>{assert.equal(time,new Date(now).toISOString());calls.push('mount');return()=>{calls.push('remove');};},
 print:()=>{calls.push('print');},finished:()=>{calls.push('finished');},
 afterPrint:cb=>{after=cb;return()=>{calls.push('unlisten-after');};},beforePrint:cb=>{before=cb;return()=>{calls.push('unlisten-before');};},
 expireAfter:(ms,cb)=>{ttl=ms;expire=cb;return()=>{calls.push('cancel-timer');};}};
 return {h,calls,after:()=>after(),before:()=>before(),expire:()=>expire(),ttl:()=>ttl};
}
test('explicit print refreshes first and prepares only the fresh response; cleanup is idempotent',async()=>{
 const f=host(),c=new AbortController();let requests=0;
 const cleanup=await printAssessment(async()=>{requests++;f.calls.push('fetch');return cvOnly;},f.h,c.signal);
 assert.equal(requests,1);assert.deepEqual(f.calls,['fetch','mount','print']);assert.equal(f.ttl(),300000);
 f.after();cleanup();assert.equal(f.calls.filter(x=>x==='remove').length,1);assert.equal(f.calls.filter(x=>x==='finished').length,1);
});
test('authorization failure and changed/expired context never print',async()=>{
 const f=host(),c=new AbortController();
 await assert.rejects(printAssessment(async()=>{throw Error('denied');},f.h,c.signal));assert.deepEqual(f.calls,[]);
 c.abort();await assert.rejects(printAssessment(async()=>cvOnly,f.h,c.signal));assert.deepEqual(f.calls,[]);
 const expired={interview:{state:'available',retention_deadline:new Date(now-1).toISOString()}} as ConsolidatedReport;
 await assert.rejects(printAssessment(async()=>expired,f.h,new AbortController().signal));assert.deepEqual(f.calls,[]);
});
test('expiry, context abortion and native failures remove the temporary document',async()=>{
 for(const event of ['expiry','abort','failure']){
  const f=host(),c=new AbortController();
  if(event==='failure')f.h.print=()=>{throw Error('unsupported');};
  if(event==='failure')await assert.rejects(printAssessment(async()=>cvOnly,f.h,c.signal));
  else{await printAssessment(async()=>cvOnly,f.h,c.signal);if(event==='expiry')f.expire();else c.abort();}
  assert.equal(f.calls.filter(x=>x==='remove').length,1);assert.equal(f.calls.filter(x=>x==='finished').length,1);
 }
});
test('available evidence expires at retention deadline and is checked again before native printing',async()=>{
 const f=host(),c=new AbortController();let clock=now;f.h.now=()=>clock;
 const report={interview:{state:'available',retention_deadline:new Date(now+5000).toISOString()}} as ConsolidatedReport;
 await printAssessment(async()=>report,f.h,c.signal);assert.equal(f.ttl(),5000);
 clock+=6000;f.before();assert.ok(f.calls.includes('remove'));
});
test('print stylesheet isolates the direct-body report and permits pagination and long evidence',()=>{
 const css=readFileSync(new URL('../src/index.css',import.meta.url),'utf8');
 assert.match(css,/@media print/);assert.match(css,/body > \* \{ display: none !important/);
 assert.match(css,/body > #talenttrace-assessment-print \{ display: block !important/);
 assert.match(css,/overflow-wrap: anywhere/);assert.match(css,/break-after: avoid-page/);
 assert.match(css,/table-header-group/);assert.match(css,/break-inside: auto/);
 const component=readFileSync(new URL('../src/components/ConsolidatedAssessment.ts',import.meta.url),'utf8');
 assert.match(component,/querySelectorAll\('details'\).*d.open=true/);
 assert.match(component,/onClick:\(\)=>void printReport\(\)/);
});
test('only one report can prepare a print copy at a time',async()=>{
 const a=host(),b=host();const cleanup=await printAssessment(async()=>cvOnly,a.h,new AbortController().signal);
 await assert.rejects(printAssessment(async()=>cvOnly,b.h,new AbortController().signal));assert.deepEqual(b.calls,[]);
 cleanup();const second=await printAssessment(async()=>cvOnly,b.h,new AbortController().signal);second();
});
