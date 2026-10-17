import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';
import ApplicationDiscovery,{DiscoveryCards} from '../src/components/ApplicationDiscovery.ts';
import CandidateComparison from '../src/components/CandidateComparison.ts';
import {fetchApplications,validDiscovery} from '../src/api/applicationDiscovery.ts';
import type {ApplicationDiscovery as Discovery,DiscoveredApplication} from '../src/api/applicationDiscovery';
const id='00000000-0000-4000-8000-000000000001',other='00000000-0000-4000-8000-000000000002';
function item():DiscoveredApplication{return {job_id:id,batch_id:id,upload_id:id,kind:'scored',label:'Scored',detail:'Saved evidence.',
 evidence_revision:2,recorded_revisions:[2],report_available:true,comparison_available:true};}
function fixture():Discovery{return {job_id:id,criteria_revision:2,notice:'Persisted records only; interview access is revalidated.',applications:[item()]};}
test('scored, unscored and snapshot-only identities remain discoverable with explicit labels',()=>{
 const d=fixture();d.applications.push({...item(),upload_id:other,kind:'historical_snapshot',label:'Historical selection snapshot'});
 assert.ok(validDiscovery(d,id,2));const html=renderToStaticMarkup(h(DiscoveryCards,{discovery:d}));
 assert.match(html,/Historical selection snapshot/);assert.equal((html.match(/View consolidated assessment/g)??[]).length,2);
 const u=fixture();u.applications[0]={...item(),kind:'unscored',label:'Screening evidence available; not scored',detail:'Requirement breakdown absent.'};
 const rendered=renderToStaticMarkup(h(DiscoveryCards,{discovery:u}));assert.match(rendered,/not scored/);assert.match(rendered,/Requirement breakdown absent/);
 assert.doesNotMatch(rendered,/0.00 \/ 100/);
});
test('historical revision and restricted evidence have honest report/comparison availability',()=>{
 const d=fixture();d.applications=[{...item(),kind:'historical_snapshot',label:'Historical selection snapshot',evidence_revision:1,recorded_revisions:[1],comparison_available:false},
 {...item(),upload_id:other,kind:'unavailable',label:'Evidence unavailable or restricted',evidence_revision:null,recorded_revisions:[],report_available:false,comparison_available:false}];
 assert.ok(validDiscovery(d,id,2));const html=renderToStaticMarkup(h(DiscoveryCards,{discovery:d}));
 assert.equal((html.match(/View consolidated assessment/g)??[]).length,1);assert.match(html,/Not comparable with current/);assert.match(html,/No validated report available/);
});
test('metadata validation rejects foreign jobs, duplicate identities, stale revisions and invalid eligibility',()=>{
 const d=fixture();assert.ok(!validDiscovery(d,other,2));assert.ok(!validDiscovery(d,id,3));
 assert.ok(!validDiscovery({...d,applications:[item(),item()]},id,2));
 assert.ok(!validDiscovery({...d,applications:[{...item(),job_id:other}]},id,2));
 assert.ok(!validDiscovery({...d,applications:[{...item(),report_available:false}]},id,2));
 assert.ok(!validDiscovery({...d,applications:[{...item(),evidence_revision:1}]},id,2));
});
test('fresh discovery GET includes credentials and no cache; errors reveal no private response',async()=>{
 const old=fetch;let calls=0;
 globalThis.fetch=async(url,init)=>{calls++;assert.match(String(url),/assessment-applications$/);assert.equal(init?.method,undefined);
 assert.equal(init?.cache,'no-store');assert.equal(init?.credentials,'include');return new Response(JSON.stringify(fixture()));};
 try{assert.deepEqual(await fetchApplications(id,2),fixture());assert.equal(calls,1);}finally{globalThis.fetch=old;}
 globalThis.fetch=async()=>new Response('private email or source',{status:403});
 try{await assert.rejects(fetchApplications(id,2),e=>e instanceof Error&&!e.message.includes('private'));}finally{globalThis.fetch=old;}
});
test('discovery is explicit and independent of successful current score batch loading',()=>{
 const html=renderToStaticMarkup(h(ApplicationDiscovery,{jobId:id,revision:2}));assert.match(html,/Load application evidence/);
 assert.doesNotMatch(html,/View consolidated assessment/);
 const source=readFileSync(new URL('../src/components/SavedScores.ts',import.meta.url),'utf8');
 assert.match(source,/h\(ApplicationDiscovery,\{jobId,revision\}\)/);assert.doesNotMatch(source,/batches&&h\(ApplicationDiscovery/);
 const empty=renderToStaticMarkup(h(DiscoveryCards,{discovery:{...fixture(),applications:[]}}));assert.match(empty,/does not establish that no CV files exist/);
});
test('comparison selectors accept exact snapshot identities without a mutable score batch',()=>{
 const applications=[{...item(),kind:'historical_snapshot' as const,label:'Historical selection snapshot'}, {...item(),upload_id:other}];
 const html=renderToStaticMarkup(h(CandidateComparison,{jobId:id,revision:2,applications}));
 assert.match(html,/Saved application 1/);assert.match(html,/Saved application 2/);assert.match(html,new RegExp(`${id}/${other}`));
});
