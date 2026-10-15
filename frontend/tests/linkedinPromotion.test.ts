import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";
import ts from "typescript";
import {prepareLinkedInDraft} from "../src/api/jobPublishing.ts";

const result:any = {job_description: {title: "Synthetic engineer", summary: "Build APIs", responsibilities: ["Test"], required_skills: ["Python"], preferred_skills: [], qualifications: ["Engineering"]}};

test("preparation uses authenticated route and validates prepared rather than published", async t => {
  const calls:any[]=[];
  t.mock.method(globalThis,"fetch",async (url:any,init:any)=>{calls.push([url,init]); return Response.json({destination:"linkedin",status:"prepared",mode:"manual",announcement:"Synthetic job"});});
  assert.equal((await prepareLinkedInDraft(result,{},"synthetic-id")).status,"prepared");
  assert.match(calls[0][0],/linkedin\/prepare$/);
  assert.equal(calls[0][1].credentials,"include");
  assert.equal(calls[0][1].headers.get("X-TalentTrace-Request"),"1");
  assert.equal(calls.length,1);
});

for (const status of [401,403,409,429,502,503]) test(`preparation HTTP ${status} never claims publication or retries`,async t=>{
  let calls=0;
  t.mock.method(globalThis,"fetch",async()=>{calls++;return Response.json({error:"PRIVATE_TOKEN"},{status});});
  await assert.rejects(prepareLinkedInDraft(result,{},"synthetic-id"),e=>!String(e).includes("PRIVATE_TOKEN"));
  assert.equal(calls,1);
});

test("published response is rejected by manual preparation contract",async t=>{
  t.mock.method(globalThis,"fetch",async()=>Response.json({destination:"linkedin",status:"published",mode:"manual",announcement:"Synthetic"}));
  await assert.rejects(prepareLinkedInDraft(result,{},"synthetic-id"));
});

function harness(confirm:boolean) {
  const states:any[]=[],refs:any[]=[];let index=0,refIndex=0,calls=0,copies=0;
  const hooks={createElement:(type:any,props:any,...children:any[])=>({type,props:{...props,children}}),
    useState:(value:any)=>{const i=index++;if(!(i in states)) states[i]=value;return [states[i],(v:any)=>{states[i]=v;}];},
    useRef:(value:any)=>{const i=refIndex++;return refs[i]??(refs[i]={current:value});}};
  const exports:any={};
  const compiled=ts.transpileModule(readFileSync(new URL("../src/components/LinkedInPromotion.ts",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  runInNewContext(compiled,{exports,require:(n:string)=>n==="react"?hooks:{prepareLinkedInDraft:async()=>{calls++;return {announcement:"Synthetic preview"};}},
    window:{confirm:()=>confirm},navigator:{clipboard:{writeText:async()=>{copies++;}}}});
  const render=()=>{index=0;refIndex=0;return exports.LinkedInPromotion({result,jobId:"synthetic-id"});};
  function find(node:any,label:string):any {if(!node||typeof node!=="object") return null;if(node.type==="button"&&node.props.children.includes(label)) return node;for(const child of (node.props?.children??[]).flat(Infinity)){const found=find(child,label);if(found)return found;}return null;}
  async function flush(){for(let i=0;i<12;i++) await Promise.resolve();}
  return {render,find,flush,counts:()=>({calls,copies}),states};
}

test("double preparation clicks call MCP once; cancellation copies nothing",async()=>{
  const h=harness(false),button=h.find(h.render(),"Prepare for LinkedIn");
  button.props.onClick();button.props.onClick();await h.flush();
  const tree=h.render();h.find(tree,"Copy reviewed announcement").props.onClick();await h.flush();
  assert.deepEqual(h.counts(),{calls:1,copies:0});
  assert.match(JSON.stringify(tree),/Prepared for LinkedIn sharing/);
  assert.doesNotMatch(JSON.stringify(tree),/Published successfully/);
});

test("confirmed copy remains a manual action without a publication call",async()=>{
  const h=harness(true);h.find(h.render(),"Prepare for LinkedIn").props.onClick();await h.flush();
  h.find(h.render(),"Copy reviewed announcement").props.onClick();await h.flush();
  assert.deepEqual(h.counts(),{calls:1,copies:1});
  assert.match(h.states[1],/Paste into LinkedIn/);
});
