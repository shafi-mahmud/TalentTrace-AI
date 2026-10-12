import { createElement as h, lazy, Suspense, useRef, useState } from "react";
import { exchangeInvitation } from "../api/livekitInterview.ts";
const LiveInterviewPage=lazy(()=>import("./LiveInterviewPage"));

export default function CandidateInterview({initialToken}:{initialToken:string|null}) {
  const token=useRef(initialToken);const pending=useRef(false);
  const [ready,setReady]=useState(!initialToken);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function accept() {if(!token.current || pending.current)return;pending.current=true;setBusy(true);setError("");
    const raw=token.current;token.current=null;
    try {await exchangeInvitation(raw);setReady(true);}
    catch(failure){setError(`${failure instanceof Error?failure.message:"Invitation delivery was not confirmed."} If delivery was interrupted, reload once to use an established browser session; do not repeat the invitation in another browser.`);}
    finally{pending.current=false;setBusy(false);}}
  if(ready)return h(Suspense,{fallback:h("p",{role:"status"},"Loading interview…")},
    h(LiveInterviewPage,{candidate:true,onBack:()=>{window.location.assign("/");}}));
  return h("main",{className:"app-shell"},h("section",{className:"card"},h("h1",null,"Candidate interview invitation"),
    h("p",null,"Use only synthetic test data. Accepting claims this one-use link for this browser. No recruiter login is needed."),
    h("button",{disabled:busy || !token.current,onClick:()=>void accept()},"Accept invitation"),error && h("p",{role:"alert"},error)));
}
