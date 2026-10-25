import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import {cvProviderReady} from '../src/api/cvProvider.ts';
import { isImportedDiscovery, screenImportedBatch } from '../src/api/importedBatches.ts';
const job = '00000000-0000-4000-8000-000000000001', batch = '00000000-0000-4000-8000-000000000002', upload = '00000000-0000-4000-8000-000000000003', reference = 'TT-JOB-0123456789ABCDEF';
const row = { batch_id: batch, upload_ids: [upload], availability: 'available', screening_status: 'not_screened', review_token: 'a'.repeat(64) };
const discovery = { job_id: job, job_reference: reference, criteria_revision: 2, batches: [row] };
const snapshot = { job_reference: reference, job_title: 'Synthetic', criteria_confirmed: true, criteria: [{ criterion_id: 'python', description: 'Python', category: 'skill', is_hard: true }] };
test('discovery validates exact owned identities without upload response fabrication or private fields', () => {
    assert.equal(isImportedDiscovery(discovery, job, reference, 2), true);
    for (const value of [{ ...discovery, job_id: batch }, { ...discovery, criteria_revision: 1 }, { ...discovery, email: 'private' }, { ...discovery, batches: [row, row] }, { ...discovery, batches: [{ ...row, upload_ids: [upload, upload] }] }, { ...discovery, batches: [{ ...row, path: 'private' }] }, { ...discovery, batches: [{ ...row, review_token: null }] }, { ...discovery, batches: [{ ...row, availability: 'unavailable' }] }])
        assert.equal(isImportedDiscovery(value, job, reference, 2), false);
    assert.equal(isImportedDiscovery({ ...discovery, batches: [{ ...row, availability: 'unavailable', review_token: null }] }, job, reference, 2), true);
});
test('unavailable and unreviewed selections reject before HTTP', async () => {
    await assert.rejects(() => screenImportedBatch(discovery as any, { ...row } as any, snapshot as any), /review/);
    const unavailable = { ...row, availability: 'unavailable', review_token: null };
    await assert.rejects(() => screenImportedBatch({ ...discovery, batches: [unavailable] } as any, unavailable as any, snapshot as any), /review/);
});
function harness({ fail = false, hold = false, holdRead = false, supplied: anyValue = discovery } = {}) {
    const states: any[] = [], refs: any[] = [], effects: Array<() => void> = [];
    let si = 0, ri = 0, ei = 0, reads = 0, writes = 0, resolve: any;
    const props: any = { jobId: job, reference, revision: 2, snapshot, selection:{provider:"ollama:qwen2.5:1.5b",externalConfirmed:false}, disabled: false, onBusy(v: boolean) { props.busy = v; }, onResult(v: any) { props.result = v; } };
    const deps: any[] = [], cleanups: any[] = [];
    const hooks = { createElement: h, useState(v: any) { const i = si++; if (!(i in states))
            states[i] = v; return [states[i], (x: any) => states[i] = x]; }, useRef(v: any) { return refs[ri++] ?? (refs[ri - 1] = { current: v }); }, useLayoutEffect(f: () => void, d: any[]) { const i = ei++; if (!deps[i] || d.some((v, k) => v !== deps[i][k])) {
            deps[i] = d;
            effects.push(() => { cleanups[i]?.(); cleanups[i] = f(); });
        } } };
    const source = ts.transpileModule(readFileSync(new URL('../src/components/ImportedBatches.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, exports: any = {};
    runInNewContext(source, { exports, Error, require: (name: string) => name === 'react' ? hooks : name === '../api/cvProvider.ts' ? {cvProviderReady} : { async fetchImportedBatches() { reads++; if (holdRead)
                await new Promise(r => resolve = r); return anyValue; }, async screenImportedBatch(context: any, b: any, s: any) { writes++; assert.equal(context.job_id, job); assert.equal(b.batch_id, batch); assert.equal(s, snapshot); if (hold)
                await new Promise(r => resolve = r); if (fail)
                throw Error('Screening failed. Check saved results before an explicit retry.'); return { safe: 'result' }; } } });
    function render() { si = 0; ri = 0; ei = 0; const tree = exports.default(props); effects.splice(0).forEach(f => f()); return tree; }
    function nodes(n: any): any[] { return n && typeof n === 'object' ? [n, ...[n.props?.children].flat(Infinity).flatMap(nodes)] : []; }
    function button(name: string) { return nodes(render()).find(n => n.type === 'button' && n.props.children === name); }
    const tick = async () => { for (let i = 0; i < 15; i++)
        await Promise.resolve(); };
    async function review() { button('Load imported batches').props.onClick(); await tick(); button('Review imported batch').props.onClick(); nodes(render()).find(n => n.type === 'input').props.onChange({ target: { checked: true } }); }
    return { render, button, review, tick, props, release() { resolve(); }, get reads() { return reads; }, get writes() { return writes; } };
}
test('real handlers do not auto-load, upload or screen; explicit review/ack; duplicate clicks suppressed', async () => {
    const x = harness();
    x.render();
    assert.equal(x.reads, 0);
    assert.equal(x.writes, 0);
    assert.equal(x.button('Screen imported batch'), undefined);
    x.button('Load imported batches').props.onClick();
    await x.tick();
    x.button('Review imported batch').props.onClick();
    assert.equal(x.button('Screen imported batch').props.disabled, true);
    const y = harness();
    await y.review();
    const join = y.button('Screen imported batch');
    assert.equal(join.props.disabled, false);
    join.props.onClick();
    join.props.onClick();
    await y.tick();
    assert.equal(y.writes, 1);
    assert.equal(y.props.result.safe, 'result');
    assert.equal(y.props.busy, false);
    assert.equal(y.button('Screen imported batch').props.disabled, true);
});
test('failed screening remains explicit and cannot automatically retry', async () => {
    const x = harness({ fail: true });
    await x.review();
    x.button('Screen imported batch').props.onClick();
    await x.tick();
    assert.equal(x.writes, 1);
    assert.equal(x.props.result, null);
    assert.equal(x.button('Screen imported batch').props.disabled, true);
    assert.match(renderToStaticMarkup(x.render()), /Check saved results/);
    assert.doesNotMatch(renderToStaticMarkup(x.render()), /Batch complete/);
});
test('criteria required; missing files cannot be selected; empty state is honest', async () => {
    const x = harness();
    x.props.snapshot = null;
    assert.equal(x.button('Load imported batches').props.disabled, true);
    assert.match(renderToStaticMarkup(x.render()), /Confirm the current/);
    const missing = harness({ supplied: { ...discovery, batches: [{ ...row, availability: 'unavailable', review_token: null }] } });
    missing.button('Load imported batches').props.onClick();
    await missing.tick();
    assert.equal(missing.button('Review imported batch'), undefined);
    assert.match(renderToStaticMarkup(missing.render()), /missing, changed or unsafe/);
    const empty = harness({ supplied: { ...discovery, batches: [] } });
    empty.button('Load imported batches').props.onClick();
    await empty.tick();
    assert.match(renderToStaticMarkup(empty.render()), /No imported CV batches/);
});
test('late discovery and screening responses cannot populate a changed job context', async () => {
    const read = harness({ holdRead: true });
    read.button('Load imported batches').props.onClick();
    read.props.jobId = batch;
    read.render();
    read.release();
    await read.tick();
    assert.equal(read.button('Review imported batch'), undefined);
    const write = harness({ hold: true });
    await write.review();
    write.button('Screen imported batch').props.onClick();
    write.props.jobId = batch;
    write.render();
    write.release();
    await write.tick();
    assert.equal(write.props.result, null);
    assert.equal(write.props.busy, false);
    assert.equal(write.button('Screen imported batch'), undefined);
});
