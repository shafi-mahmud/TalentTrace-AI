import { authenticatedFetch } from "./session.ts";

export interface InterviewAccess { server_url:string; token:string; expires_in:300; }
const base=(import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export async function interviewAccess(jobId:string,interviewId:string,slot:"a"|"b"):Promise<InterviewAccess> {
  let response:Response;
  try {response=await authenticatedFetch(`${base}/api/v1/jobs/${jobId}/interviews/${interviewId}/livekit-token`,{
    method:"POST",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({slot,synthetic_test_confirmed:true})});}
  catch {throw new Error("Interview access was not confirmed. Join again only when ready.");}
  if(!response.ok) throw new Error(response.status===503?"LiveKit synthetic testing is not configured."
    :response.status===409?"Review this interview against the current approved job criteria."
    :response.status===404?"Owned interview not found.":"Interview access could not be issued.");
  const value:unknown=await response.json().catch(()=>null);
  if(!value || typeof value!=="object") throw new Error("Interview access could not be validated.");
  const v=value as InterviewAccess;
  if(Object.keys(v).length!==3 || v.expires_in!==300 || typeof v.token!=="string" || v.token.length<32 || v.token.length>8192
    || !/^wss:\/\/[a-z0-9-]+\.livekit\.cloud\/?$/.test(v.server_url)) throw new Error("Interview access could not be validated.");
  return v;
}
