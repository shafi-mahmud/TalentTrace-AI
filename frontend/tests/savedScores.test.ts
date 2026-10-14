import test from 'node:test';import assert from 'node:assert/strict';
import {validSavedBatches,fetchSavedBatches,SavedScoreCards} from '../src/components/SavedScores.ts';
import {createElement as h} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const job='00000000-0000-4000-8000-000000000001';
const score={job_reference:'TT-JOB-0000000000000001',upload_id:job,screening_decision:'eligible' as const,status:'not_evaluated' as const,reason:'uncertain_evidence' as const,weights:{skill:100,experience:0,education:0},score:null,dimensions:[]};
const b={job_id:job,job_reference:score.job_reference,batch_id:job,criteria_revision:2,scoring_version:'f2-coverage-v1' as const,weights:score.weights,candidates:[score],ranking:[]};
test('saved associations and revision guard',()=>{assert.ok(validSavedBatches([b],job,2));assert.ok(!validSavedBatches([b],job,3));assert.ok(!validSavedBatches([{...b,job_id:'foreign'}],job,2));assert.ok(validSavedBatches([],job,2));});
test('eligible unscored selection keeps existing scheduling safeguards',()=>{const html=renderToStaticMarkup(h(SavedScoreCards,{batches:[b],onSelect:()=>{}}));assert.ok(html.includes('Select for interview'));assert.ok(html.includes('Not scored'));assert.ok(!html.includes('0.00 / 100'));});
test('saved loading performs GET only',async()=>{const old=fetch;globalThis.fetch=async(_,init)=>{assert.equal(init?.method,undefined);assert.equal(init?.credentials,'include');return new Response(JSON.stringify([b]));};try{assert.equal((await fetchSavedBatches(job,2)).length,1);}finally{globalThis.fetch=old;}});
