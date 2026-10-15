import { createElement as h, useRef, useState } from "react";
import { prepareLinkedInDraft } from "../api/jobPublishing.ts";
import type { JobDescriptionGenerationResponse } from "../types/jobDescription";
import type { PublishingContext } from "../types/recruiterChat";

export function LinkedInPromotion({result, context, jobId, disabled}: {
  result: JobDescriptionGenerationResponse; context?: PublishingContext; jobId?: string; disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  async function prepare() {
    if (pending.current || text || disabled || !jobId) return;
    pending.current = true; setBusy(true); setNotice("");
    try { setText((await prepareLinkedInDraft(result, context, jobId)).announcement); }
    catch { setNotice("LinkedIn preparation failed. Nothing was published."); }
    finally { pending.current = false; setBusy(false); }
  }
  async function copy() {
    if (!window.confirm("Copy this reviewed announcement for manual LinkedIn sharing? Nothing will be published by TalentTrace.")) return;
    try { await navigator.clipboard.writeText(text); setNotice("Copied. Paste into LinkedIn, review the audience and confirm Post there. Check your feed before posting again."); }
    catch { setNotice("Copy unavailable. Select and copy the preview text manually."); }
  }
  return h("section", {"aria-label": "LinkedIn promotion"},
    h("h3", null, "LinkedIn feed announcement"),
    h("p", null, "Manual sharing only. This does not create a LinkedIn Jobs listing or publish through the API."),
    h("button", {type: "button", className: "button button-secondary", disabled: disabled || busy || !!text || !jobId, onClick: () => void prepare()}, busy ? "Preparing…" : "Prepare for LinkedIn"),
    text ? h("div", null,
      h("strong", {role: "status"}, "Prepared for LinkedIn sharing — not published"),
      h("textarea", {"aria-label": "LinkedIn announcement preview", readOnly: true, rows: 12, value: text}),
      h("button", {type: "button", className: "button button-secondary", onClick: () => void copy()}, "Copy reviewed announcement"),
      h("a", {href: "https://www.linkedin.com/feed/", target: "_blank", rel: "noopener noreferrer"}, "Open LinkedIn to post manually")) : null,
    notice ? h("p", {role: "status"}, notice) : null);
}
