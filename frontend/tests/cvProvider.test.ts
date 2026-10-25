import test from 'node:test';
import assert from 'node:assert/strict';
import {cvProviderHeaders,cvProviderReady} from '../src/api/cvProvider.ts';
import {extractCandidateProfiles} from '../src/api/candidateProfiles.ts';
import {screenStoredBatch} from '../src/api/screening.ts';
test('CV selection is fail closed; never implicitly chooses cloud',()=>{
 for(const v of [undefined,{provider:'',externalConfirmed:false},{provider:'groq',externalConfirmed:false},{provider:'https://untrusted.invalid',externalConfirmed:true}]){
  assert.equal(cvProviderReady(v),false);assert.throws(()=>cvProviderHeaders(v));
 }
 assert.deepEqual(cvProviderHeaders({provider:'ollama:qwen2.5:1.5b',externalConfirmed:false}),{'X-TalentTrace-AI-Provider':'ollama:qwen2.5:1.5b'});
 assert.equal(cvProviderHeaders({provider:'groq',externalConfirmed:true})['X-TalentTrace-External-Processing'],'confirmed');
});
