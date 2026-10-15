import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";
import ts from "typescript";
import {loadApplications,markApplicationsViewed,validateApplications} from "../src/api/applications.ts";

const job="00000000-0000-4000-8000-000000000001";
const row={batch_id:"00000000-0000-4000-8000-000000000002",upload_id:"00000000-0000-4000-8000-000000000003",origin:"trusted_import" as const,available:true,is_new:true};
function summary(){return {job_id:job,received_count:1,new_count:1,unavailable_count:0,invalid_batch_count:0,applications:[row]};}

test("counts cannot mix jobs, duplicate files or falsified totals",()=>{
  assert.equal(validateApplications(summary(),job).new_count,1);
  for(const patch of [{job_id:"another"},{received_count:2},{new_count:0},{unavailable_count:1},{applications:[row,row]},{applications:[{...row,origin:"unknown"}]}])
    assert.throws(()=>validateApplications({...summary(),...patch},job));
});
test("refresh is authenticated GET; viewed writes only displayed identities",async t=>{
  const calls:any[]=[];
  t.mock.method(globalThis,"fetch",async (url:any,init:any)=>{calls.push([url,init]);return init.method==="POST"?new Response(null,{status:204}):Response.json(summary());});
  await loadApplications(job);await markApplicationsViewed(job,[row]);
  assert.equal(calls[0][1].method,undefined);
  assert.equal(calls[0][1].credentials,"include");
  assert.equal(calls[1][1].headers.get("X-TalentTrace-Request"),"1");
  assert.deepEqual(JSON.parse(calls[1][1].body),{applications:[{batch_id:row.batch_id,upload_id:row.upload_id}]});
  assert.match(calls[1][0],/applications\/viewed$/);
});
test("API errors are sanitized and never automatically repeated",async t=>{
  let calls=0;t.mock.method(globalThis,"fetch",async()=>{calls++;return Response.json({email:"PRIVATE_VALUE"},{status:500});});
  await assert.rejects(loadApplications(job),e=>!String(e).includes("PRIVATE_VALUE"));assert.equal(calls,1);
  await assert.rejects(markApplicationsViewed(job,[row]),e=>!String(e).includes("PRIVATE_VALUE"));assert.equal(calls,2);
});

function harness(initial:any=summary(),fail=false) {
  const states:any[]=[],refs:any[]=[],effects:any[]=[];let index=0,refIndex=0,loads=0,marks=0;
  let resolveLoad:(value:any)=>void=()=>{};
  let next:any=initial;
  const hooks={useState:(value:any)=>{const i=index++;if(!(i in states)) states[i]=value;return [states[i],(v:any)=>{states[i]=v;}];},
    useRef:(value:any)=>{const i=refIndex++;return refs[i]??(refs[i]={current:value});},useEffect:(fn:any)=>{effects.push(fn);}};
  const exports:any={};
  const jsx=(type:any,props:any)=>({type,props});
  const compiled=ts.transpileModule(readFileSync(new URL("../src/components/ApplicationNotifications.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  runInNewContext(compiled,{exports,require:(name:string)=>name==="react"?hooks:name==="react/jsx-runtime"?{jsx,jsxs:jsx,Fragment:"fragment"}:{
    loadApplications:async()=>{loads++;if(fail) throw new Error("PRIVATE");if(next===null) return new Promise(r=>{resolveLoad=r;});return next;},
    markApplicationsViewed:async(_job:any,rows:any)=>{marks++;assert.equal(rows.length,1);next={...initial,new_count:0,applications:[{...row,is_new:false}]};}}});
  function render(){index=0;refIndex=0;return exports.default({jobId:job});}
  function find(node:any,p:(n:any)=>boolean):any {if(!node||typeof node!=="object")return null;if(p(node))return node;for(const c of [node.props?.children].flat(Infinity)){const match=find(c,p);if(match)return match;}return null;}
  const click=(label:string)=>find(render(),n=>n.type==="button"&&n.props.children===label).props.onClick();
  async function flush(){for(let i=0;i<15;i++)await Promise.resolve();}
  render();const cleanup=effects[0]();
  return {render,click,flush,cleanup,find,counts:()=>({loads,marks}),resolve:(v:any)=>resolveLoad(v)};
}
test("new badge, application list and explicit persistent viewed action",async()=>{
  const h=harness();await h.flush();assert.match(JSON.stringify(h.render()),/new/);
  h.click("View applications");h.click("Mark listed applications as viewed");await h.flush();
  assert.deepEqual(h.counts(),{loads:2,marks:1});assert.match(JSON.stringify(h.render()),/Viewed/);
});
test("zero, loading and failure states never invent a count",async()=>{
  const empty=harness({...summary(),received_count:0,new_count:0,applications:[]});await empty.flush();empty.click("View applications");assert.match(JSON.stringify(empty.render()),/No applications received/);
  const busy=harness(null);assert.match(JSON.stringify(busy.render()),/Updating applications/);
  busy.cleanup();busy.resolve(summary());await busy.flush();assert.doesNotMatch(JSON.stringify(busy.render()),/CVs received/);
  const failed=harness(summary(),true);await failed.flush();assert.match(JSON.stringify(failed.render()),/Applications unavailable/);assert.doesNotMatch(JSON.stringify(failed.render()),/PRIVATE/);
});
