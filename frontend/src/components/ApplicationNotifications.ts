import { createElement as h, Fragment, useEffect, useRef, useState } from 'react';
import { loadApplications, markApplicationsViewed } from '../api/applications.ts';
import type { Applications } from '../api/applications.ts';
export function ApplicationSummary({data}:{data:Applications}) {
    const imported=data.applications.filter(row=>row.origin==='trusted_import').length;
    const native=data.received_count-imported;
    const metrics=[['CVs received',data.received_count],['New / unviewed',data.new_count],
      ['Available CVs',data.received_count-data.unavailable_count],['Imported CVs needing attention',data.unavailable_count]] as const;
    return h(Fragment,null,
      h('dl',{className:'application-metrics'},...metrics.map(([label,count])=>h('div',{className:'application-metric',key:label},
        h('dt',null,label),h('dd',null,count)))),
      h('table',{className:'application-breakdown'},h('caption',null,'Application source breakdown'),
        h('thead',null,h('tr',null,...['Source','Applications','Share of received'].map(label=>h('th',{key:label,scope:'col'},label)))),
        h('tbody',null,...([['Native upload',native],['Trusted import',imported]] as const).map(([label,count])=>h('tr',{key:label},
          h('th',{scope:'row'},label),h('td',null,count),h('td',null,h('meter',{min:0,max:Math.max(1,data.received_count),value:count,'aria-label':label},count)))))));
}
export default function ApplicationNotifications({ jobId }: {
    jobId: string;
}) {
    const [data, setData] = useState<Applications | null>(null);
    const [busy, setBusy] = useState(false), [error, setError] = useState(''), [limit, setLimit] = useState(25);
    const sequence = useRef(0), pending = useRef(false);
    async function refresh() {
        if (pending.current)
            return;
        pending.current = true;
        const current = ++sequence.current;
        setBusy(true);
        setError('');
        try {
            const next = await loadApplications(jobId);
            if (current === sequence.current)
                setData(next);
        }
        catch {
            if (current === sequence.current)
                setError('Applications unavailable. Refresh before acknowledging.');
        }
        finally {
            if (current === sequence.current) {
                pending.current = false;
                setBusy(false);
            }
        }
    }
    useEffect(() => { setData(null); setLimit(25); pending.current = false; void refresh(); return () => { sequence.current++; pending.current = false; }; }, [jobId]);
    const current = data?.job_id === jobId ? data : null;
    const displayed = current?.applications.slice(0, limit) ?? [];
    async function viewed() {
        if (!current || pending.current || error)
            return;
        pending.current = true;
        const ticket = ++sequence.current;
        setBusy(true);
        setError('');
        // Snapshot only what was displayed when the recruiter clicked, never later arrivals.
        const snapshot = displayed;
        try {
            await markApplicationsViewed(jobId, snapshot);
            if (ticket === sequence.current) {
                pending.current = false;
                await refresh();
            }
        }
        catch {
            if (ticket === sequence.current) {
                pending.current = false;
                setBusy(false);
                setError('Viewed status was not confirmed. Refresh before trying again.');
            }
        }
    }
    return h('section',{className:'card application-notifications','aria-label':'Application notifications'},
      h('h3',null,'Applications and notifications'),
      h('p',{className:'helper-text'},'New means not explicitly marked viewed. Opening Home or refreshing does not acknowledge applications.'),
      busy && h('p',{role:'status'},'Updating applications…'),
      error && h('p',{role:'alert',className:'error-banner'},error),
      current && (busy||error) && h('p',{role:'status'},'Last loaded snapshot — counts may be stale.'),
      !current && !busy && h('p',null,'Application counts unavailable.'),
      h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>void refresh()},'Refresh applications'),
      current && h(Fragment,null,h(ApplicationSummary,{data:current}),
        current.unavailable_count>0 && h('p',{role:'status'},'Imported CV files are missing or do not match expected metadata. Administrator review needed.'),
        current.invalid_batch_count>0 && h('p',{role:'status'},`${current.invalid_batch_count} invalid storage batches excluded from native counts; administrator review needed.`),
        !current.received_count && h('p',null,'No applications received yet.'),
        h('h4',null,'Received application list'),
        h('p',{className:'helper-text'},'Identity order, not arrival order. Arrival timestamps are unavailable; no dates are inferred from files.'),
        h('ul',{className:'application-list','aria-label':'Displayed applications'},...displayed.map((row,index)=>h('li',{key:`${row.batch_id}/${row.upload_id}`},
          `Application ${index+1} · ${row.origin==='trusted_import'?'Trusted import':'Native upload'} · ${row.available?'CV available':'CV unavailable'} · ${row.is_new?'New':'Viewed'}`))),
        displayed.length<current.received_count && h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:()=>setLimit(limit+25)},'Show more applications'),
        h('p',{className:'helper-text'},`Showing ${displayed.length} of ${current.received_count}. Only these displayed applications will be acknowledged.`),
        h('button',{type:'button',className:'button button-secondary',disabled:busy||!!error||!displayed.some(row=>row.is_new),onClick:()=>void viewed()},'Mark displayed applications as viewed')),
      h('p',{className:'helper-text'},'Screening outcome analytics unavailable here: saved scores omit complete processing-failure history. Review current results in Candidate Screening; received counts are independent of screening.'));
}
