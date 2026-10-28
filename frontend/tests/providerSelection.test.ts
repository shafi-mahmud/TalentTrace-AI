import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ProviderSelection,{defaultProvider} from '../src/components/ProviderSelection.ts';
import {listAIProviders,sendRecruiterMessage} from '../src/api/recruiterChat.ts';
const options=[{id:'groq',label:'Groq API',available:false,external:true},
 ...['qwen2.5:1.5b','smollm2:360m-instruct-q4_K_M'].map(model=>({id:'ollama:'+model,label:'Local '+model,available:false,external:false}))];
test('selector is empty until authenticated discovery; cloud disclosure stays unchecked',()=>{
 const base={value:'',consent:false,disabled:false,onChange(){},onConsent(){}};
 const html=renderToStaticMarkup(h(ProviderSelection,base));
 assert.match(html,/Choose AI/);assert.match(html,/JD provider selection is separate from CV screening/);
 assert.doesNotMatch(html,/checked=""/);
 const cloud=renderToStaticMarkup(h(ProviderSelection,{...base,value:'groq'}));
 assert.match(cloud,/Send JD conversation and policy context to Groq/);assert.doesNotMatch(cloud,/checked=""/);
});

test('Groq defaults only after confirmed availability; choices and pinned contexts win',()=>{
 const ready=options.map(p=>({...p,available:p.id==='groq'}));
 for(const scope of ['jd','cv']){
  assert.equal(defaultProvider([],''),'');assert.equal(defaultProvider(ready,''),'groq',scope);
  assert.equal(defaultProvider(options,''),'');
  assert.equal(defaultProvider(ready,'ollama:qwen2.5:1.5b'),'');
  assert.equal(defaultProvider(ready,'',true),'');
  assert.equal(defaultProvider(ready,'',false,false),'');
 }
});
test('authenticated capability response has strict allowlisted identities and no secret fields',async t=>{
 t.mock.method(globalThis,'fetch',async(_url,init)=>{assert.equal(init?.credentials,'include');return Response.json({providers:options});});
 assert.equal((await listAIProviders()).length,3);
 for(const data of [{providers:[...options.slice(1),{...options[0],id:'http://private.invalid'}]},
   {providers:[{...options[0],api_key:'PRIVATE'},...options.slice(1)]}]){
  t.mock.method(globalThis,'fetch',async()=>Response.json(data));await assert.rejects(listAIProviders(),/unavailable/);
 }
});
test('JD request transmits explicit selection/consent without URLs or credentials',async t=>{
 let body:any;
 t.mock.method(globalThis,'fetch',async(_url,init)=>{body=JSON.parse(String(init?.body));return Response.json({}, {status:503});});
 await assert.rejects(sendRecruiterMessage('Synthetic JD',undefined,'ollama:qwen2.5:1.5b',false));
 assert.deepEqual(body,{message:'Synthetic JD',ai_provider:'ollama:qwen2.5:1.5b',external_processing_confirmed:false});
 assert.ok(!('api_key' in body)&&!('endpoint' in body));
});

test('CV selector discloses CV transfer separately and local selection needs no cloud consent',()=>{
 const base={value:'groq',scope:'cv' as const,consent:false,disabled:false,onChange(){},onConsent(){}};
 const cloud=renderToStaticMarkup(h(ProviderSelection,base));
 assert.match(cloud,/CV AI/);assert.match(cloud,/Send CV text and derived qualifications to Groq/);assert.doesNotMatch(cloud,/checked=""/);
 assert.doesNotMatch(renderToStaticMarkup(h(ProviderSelection,{...base,value:'ollama:qwen2.5:1.5b'})),/Send CV text/);
});

import {ScoringProvenance} from '../src/components/scorePresentation.ts';
import {isAIProvenance} from '../src/api/scoring.ts';
test('saved provenance is allowlisted and never inferred for legacy scores',()=>{
 const metadata={provider:'groq' as const,model:'synthetic-model',external_processing_confirmed:true};
 assert.ok(isAIProvenance(metadata));assert.ok(isAIProvenance(null));
 assert.ok(!isAIProvenance({...metadata,token:'PRIVATE'}));
 assert.ok(!isAIProvenance({...metadata,model:'https://private.invalid'}));
 assert.ok(!isAIProvenance({...metadata,external_processing_confirmed:false}));
 assert.match(renderToStaticMarkup(h(ScoringProvenance,{provenance:metadata})),/Groq.*synthetic-model/);
 assert.match(renderToStaticMarkup(h(ScoringProvenance,{provenance:null})),/not recorded/);
});

test('provider options collapse while Groq disclosure and unchecked consent stay visible',()=>{
 const html=renderToStaticMarkup(h(ProviderSelection,{value:'groq',consent:false,disabled:false,onChange(){},onConsent(){}}));
 assert.match(html,/JD AI · Groq/);assert.ok(html.indexOf('Send JD conversation')>html.indexOf('</details>'));
 assert.doesNotMatch(html,/checked=""/);assert.match(html,/aria-label="JD AI"/);
});


test('compact JD selector can defer acknowledgement but CV consent cannot be hidden',()=>{
 const props={value:'groq',consent:false,disabled:false,showConsent:false,onChange(){},onConsent(){}};
 assert.doesNotMatch(renderToStaticMarkup(h(ProviderSelection,props)),/type="checkbox"/);
 assert.match(renderToStaticMarkup(h(ProviderSelection,{...props,scope:'cv'})),/Send CV text and derived qualifications/);
});
