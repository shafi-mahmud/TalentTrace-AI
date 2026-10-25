import type {CvAISelection} from "./cvProvider.ts";
import { authenticatedFetch } from './session.ts';
import { screenStoredBatch } from './screening.ts';
import type { ReviewedJobSnapshot } from '../types/screening';
export interface ImportedBatch {
    batch_id: string;
    upload_ids: string[];
    availability: 'available' | 'unavailable';
    screening_status: 'not_screened' | 'current_results' | 'incomplete_results' | 'older_revision';
    review_token: string | null;
}
export interface ImportedDiscovery {
    job_id: string;
    job_reference: string;
    criteria_revision: number;
    batches: ImportedBatch[];
}
const base = (import.meta.env?.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function keys(v: any, names: string[]) { return v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k)); }
export function isImportedDiscovery(v: any, job: string, reference: string, revision: number): v is ImportedDiscovery {
    return keys(v, ['job_id', 'job_reference', 'criteria_revision', 'batches']) && v.job_id === job && uuid.test(job) && v.job_reference === reference && /^TT-JOB-[A-F0-9]{16}$/.test(reference) && v.criteria_revision === revision && Number.isInteger(revision) && revision > 0
        && Array.isArray(v.batches) && v.batches.length <= 100 && new Set(v.batches.map((b: any) => b?.batch_id)).size === v.batches.length
        && v.batches.every((b: any) => keys(b, ['batch_id', 'upload_ids', 'availability', 'screening_status', 'review_token']) && uuid.test(b.batch_id)
            && Array.isArray(b.upload_ids) && b.upload_ids.length >= 1 && b.upload_ids.length <= 20 && b.upload_ids.every((id: unknown) => typeof id === 'string' && uuid.test(id)) && new Set(b.upload_ids).size === b.upload_ids.length
            && ['available', 'unavailable'].includes(b.availability) && ['not_screened', 'current_results', 'incomplete_results', 'older_revision'].includes(b.screening_status)
            && (b.availability === 'available' ? typeof b.review_token === 'string' && /^[a-f0-9]{64}$/.test(b.review_token) : b.review_token === null));
}
export async function fetchImportedBatches(job: string, reference: string, revision: number): Promise<ImportedDiscovery> {
    const r = await authenticatedFetch(`${base}/api/v1/jobs/${job}/imported-batches?revision=${revision}`);
    if (!r.ok)
        throw Error('Imported batches unavailable. Confirm current criteria, reload the owned job and review stored files.');
    const v = await r.json().catch(() => null);
    if (!isImportedDiscovery(v, job, reference, revision))
        throw Error('Imported batch identities could not be validated.');
    return v;
}
export async function screenImportedBatch(context: ImportedDiscovery, batch: ImportedBatch, snapshot: ReviewedJobSnapshot, selection?:CvAISelection) {
    if (!isImportedDiscovery(context, context.job_id, context.job_reference, context.criteria_revision) || !context.batches.includes(batch) || batch.availability !== 'available' || !batch.review_token)
        throw Error('Refresh and review the imported batch first.');
    return screenStoredBatch({ job_id: context.job_id, job_reference: context.job_reference, batch_id: batch.batch_id, upload_ids: batch.upload_ids }, snapshot, context.criteria_revision, batch.review_token,selection);
}
