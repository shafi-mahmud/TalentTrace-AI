import { createElement as h, useLayoutEffect, useRef, useState } from 'react';
import { fetchImportedBatches, screenImportedBatch } from '../api/importedBatches.ts';
import type { ImportedDiscovery, ImportedBatch } from '../api/importedBatches.ts';
import type { ReviewedJobSnapshot, BatchScreeningResponse } from '../types/screening';
const labels = { not_screened: 'Not screened', current_results: 'Saved results for current revision', incomplete_results: 'Incomplete saved results; review before retrying', older_revision: 'Older revision results; current review required' };
export default function ImportedBatches({ jobId, reference, revision, snapshot, disabled, onBusy, onResult }: {
    jobId: string;
    reference: string;
    revision: number;
    snapshot: ReviewedJobSnapshot | null;
    disabled: boolean;
    onBusy: (v: boolean) => void;
    onResult: (v: BatchScreeningResponse | null) => void;
}) {
    const [value, setValue] = useState<ImportedDiscovery | null>(null), [selected, setSelected] = useState<ImportedBatch | null>(null), [ack, setAck] = useState(false), [attempted, setAttempted] = useState(false), [loading, setLoading] = useState(false), [error, setError] = useState('');
    const pending = useRef(false), generation = useRef(0);
    useLayoutEffect(() => { generation.current++; setValue(null); setSelected(null); setAck(false); setAttempted(false); setError(''); setLoading(false); return () => { generation.current++; }; }, [jobId, reference, revision, snapshot]);
    async function load() {
        if (pending.current || disabled || !snapshot)
            return;
        pending.current = true;
        setLoading(true);
        setError('');
        const n = generation.current;
        try {
            const v = await fetchImportedBatches(jobId, reference, revision);
            if (n === generation.current) {
                setValue(v);
                setSelected(null);
                setAck(false);
                setAttempted(false);
            }
        }
        catch {
            if (n === generation.current) {
                setValue(null);
                setError('Imported batches unavailable. Reload current criteria and check stored files.');
            }
        }
        finally {
            pending.current = false;
            if (n === generation.current)
                setLoading(false);
        }
    }
    async function screen() {
        if (pending.current || disabled || !snapshot || !value || !selected || !ack || attempted)
            return;
        pending.current = true;
        setAttempted(true);
        setError('');
        setLoading(true);
        onBusy(true);
        onResult(null);
        const n = generation.current;
        try {
            const result = await screenImportedBatch(value, selected, snapshot);
            if (n === generation.current)
                onResult(result);
        }
        catch (e) {
            if (n === generation.current)
                setError(e instanceof Error ? e.message : 'Screening failed. Check saved results before an explicit retry.');
        }
        finally {
            pending.current = false;
            if (n === generation.current) {
                setLoading(false);
                setAck(false);
            }
            onBusy(false);
        }
    }
    return h('section', { className: 'card', 'aria-label': 'Previously imported CV batches' }, h('h2', null, 'Previously imported CV batches'), h('p', null, 'Select stored applications for this job. No upload or duplicate import is performed. Screening and explicit retries may consume LLM quota; no automatic retry.'), !snapshot && h('p', { role: 'status' }, 'Confirm the current job criteria and weights first.'), h('button', { type: 'button', className: 'button button-secondary', disabled: disabled || loading || !snapshot, onClick: () => void load() }, loading ? 'Working…' : value ? 'Refresh imported batches' : 'Load imported batches'), error && h('p', { role: 'alert', className: 'error-banner' }, error), value && h('div', null, h('p', null, `Job ${value.job_reference} · criteria revision ${value.criteria_revision}`), !value.batches.length && h('p', null, 'No imported CV batches found for this job.'), ...value.batches.map(b => h('article', { key: b.batch_id, className: 'candidate-card' }, h('p', null, `Batch ${b.batch_id} · ${b.upload_ids.length} application(s)`), h('p', null, labels[b.screening_status]), b.availability === 'unavailable' ? h('p', { role: 'status' }, 'Unavailable: stored files are missing, changed or unsafe. Operator review is required.') :
        h('div', null, h('details', null, h('summary', null, 'Verified application identities'), ...b.upload_ids.map(id => h('p', { key: id }, id))), h('button', { type: 'button', className: 'button button-secondary', disabled: disabled || loading || attempted, onClick: () => { setSelected(b); setAck(false); setAttempted(false); setError(''); } }, selected === b ? 'Batch selected' : 'Review imported batch')))), selected && h('div', { className: 'session-confirmation', 'aria-label': 'Review imported screening' }, h('p', null, `Screen batch ${selected.batch_id} against the confirmed criteria above. Existing results may be replaced for this revision.`), h('label', null, h('input', { type: 'checkbox', checked: ack, disabled: disabled || loading || attempted, onChange: (e: {
            target: {
                checked: boolean;
            };
        }) => setAck(e.target.checked) }), ' I reviewed this batch and current criteria. Screening or retry may consume LLM quota.'), h('button', { type: 'button', className: 'button button-primary', disabled: disabled || loading || attempted || !ack, onClick: () => void screen() }, 'Screen imported batch'), attempted && h('p', { role: 'status' }, 'Attempt completed or unconfirmed. Check the results below and saved scores. Refresh imported batches before considering another explicit attempt.'))));
}
