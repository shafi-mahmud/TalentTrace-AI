import {useEffect, useRef, useState} from "react";
import {loadApplications, markApplicationsViewed} from "../api/applications.ts";
import type {Applications} from "../api/applications.ts";

export default function ApplicationNotifications({jobId, refreshKey}: {jobId: string; refreshKey?: string}) {
  const [data,setData] = useState<Applications | null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [open,setOpen] = useState(false);
  const sequence = useRef(0);
  async function refresh() {
    const current = ++sequence.current;
    setBusy(true); setError("");
    try {const next=await loadApplications(jobId); if (current===sequence.current) setData(next);}
    catch {if (current===sequence.current) setError("Applications unavailable. Try Refresh.");}
    finally {if (current===sequence.current) setBusy(false);}
  }
  useEffect(()=>{setData(null); void refresh(); return ()=>{sequence.current++;};},[jobId,refreshKey]);
  async function viewed() {
    if (!data || busy) return;
    const current = ++sequence.current;
    setBusy(true); setError("");
    try {
      await markApplicationsViewed(jobId,data.applications);
      if (current===sequence.current) await refresh();
    } catch {if(current===sequence.current) {setError("Viewed status was not confirmed. Refresh before trying again.");setBusy(false);}}
  }
  const current = data?.job_id === jobId ? data : null;
  return <section className="card" aria-label="Application notifications">
    <h2>Applications {current && current.new_count > 0 && <span className="demo-badge">{current.new_count} new</span>}</h2>
    {current && <p>CVs received: <strong>{current.received_count}</strong> · New applications: <strong>{current.new_count}</strong></p>}
    {busy && <p role="status">Updating applications…</p>}
    {error && <p role="alert">{error}</p>}
    {error && current && <p className="helper-text">Showing last loaded counts.</p>}
    <button type="button" className="button button-secondary" disabled={busy} onClick={()=>void refresh()}>Refresh applications</button>
    {current && <>
      <button type="button" className="button button-secondary" disabled={busy} onClick={()=>setOpen(!open)}>{open ? "Hide applications" : "View applications"}</button>
      {open && <>
        <button type="button" className="button button-secondary" disabled={busy || !current.new_count} onClick={()=>void viewed()}>Mark listed applications as viewed</button>
        {!current.received_count && <p>No applications received yet.</p>}
        {current.unavailable_count > 0 && <p role="status">{current.unavailable_count} imported CV files unavailable. Administrator review needed.</p>}
        {current.invalid_batch_count > 0 && <p role="status">{current.invalid_batch_count} storage batches need review and are excluded from native CV counts.</p>}
        <ul aria-label="Received applications">{current.applications.map((row,index)=><li key={`${row.batch_id}/${row.upload_id}`}>
          Application {index+1} · {row.origin==="trusted_import" ? "Imported" : "Uploaded"} · {row.available ? "CV available" : "CV unavailable"}{row.is_new ? " · New" : " · Viewed"}
        </li>)}</ul>
        <p className="helper-text">Received in this workspace. New means not marked viewed; screening is separate.</p>
      </>}
    </>}
  </section>;
}
