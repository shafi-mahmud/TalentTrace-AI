import { authenticatedFetch } from "./session.ts";

export interface InterviewAccess { server_url:string; token:string; expires_in:number; }
export class InterviewAccessError extends Error {}
export function supportedLiveKitURL(url:string,development=false,pageHost=''):boolean {
  return /^wss:\/\/[a-z0-9-]+\.livekit\.cloud\/?$/.test(url)
    || (development && pageHost==='127.0.0.1' && url==='ws://127.0.0.1:7880');
}
const base=(import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export function takeInvitation(location:Location, history:History):string|null {
  const token=new URLSearchParams(location.hash.slice(1)).get("invite");
  if(location.hash)history.replaceState(null,"",location.pathname);
  return token && /^[A-Za-z0-9_-]{43}$/.test(token)?token:null;
}
export async function interviewAccess(jobId:string,interviewId:string):Promise<InterviewAccess> {
  return requestAccess(`${base}/api/v1/jobs/${jobId}/interviews/${interviewId}/livekit-token`);
}
export async function candidateAccess():Promise<InterviewAccess> {
  return requestAccess(`${base}/api/v1/interview-access/livekit-token`);
}
async function requestAccess(url:string):Promise<InterviewAccess> {
  let response:Response;
  try {response=await fetch(url,{
    method:"POST",credentials:"include",cache:"no-store",headers:{"Content-Type":"application/json","X-TalentTrace-Request":"1"},body:JSON.stringify({synthetic_test_confirmed:true})});}
  catch {throw new InterviewAccessError("Interview access was not confirmed. Join again only when ready.");}
  if(!response.ok) throw new InterviewAccessError(response.status===503?"LiveKit synthetic testing is not configured."
    :response.status===401?"Interview access is invalid, expired or revoked. Request a replacement invitation or sign in as the recruiter."
    :response.status===409?"Interview join window is closed, or its criteria need review."
    :response.status===404?"Owned interview not found.":"Interview access could not be issued.");
  const value:unknown=await response.json().catch(()=>null);
  if(!value || typeof value!=="object") throw new InterviewAccessError("Interview access could not be validated.");
  const v=value as InterviewAccess;
  if(Object.keys(v).length!==3 || !Number.isInteger(v.expires_in) || v.expires_in<1 || v.expires_in>300 || typeof v.token!=="string" || v.token.length<32 || v.token.length>8192
    || !supportedLiveKitURL(v.server_url,import.meta.env?.DEV,globalThis.location?.hostname)) throw new InterviewAccessError("Interview access could not be validated.");
  return v;
}

export async function invitation(jobId:string,interviewId:string):Promise<{token:string;expires_at:string}> {
  const response=await authenticatedFetch(`${base}/api/v1/jobs/${jobId}/interviews/${interviewId}/invitation`,{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expires_in_hours:48})});
  if(!response.ok)throw new Error("Invitation was not confirmed. Check configuration and interview status before trying again.");
  const value=await response.json();
  if(!value || !/^[A-Za-z0-9_-]{43}$/.test(value.token) || !Number.isFinite(Date.parse(value.expires_at)))throw new Error("Invitation could not be validated.");
  return value;
}
export async function revokeInvitation(jobId:string,interviewId:string) {
  const response=await authenticatedFetch(`${base}/api/v1/jobs/${jobId}/interviews/${interviewId}/invitation/revoke`,{method:"POST"});
  if(!response.ok)throw new Error("Access revocation needs attention. Do not share the invitation; live disconnection was not confirmed.");
}
export async function exchangeInvitation(token:string) {
  const response=await fetch(`${base}/api/v1/interview-access/exchange`,{method:"POST",credentials:"include",cache:"no-store",
    headers:{"Content-Type":"application/json","X-TalentTrace-Request":"1"},body:JSON.stringify({token})});
  if(!response.ok)throw new Error(response.status===409?"Invitation already used. Use the original browser or request a replacement.":"Invitation is invalid, expired or revoked.");
}
export async function candidateStatus() {
  const response=await fetch(`${base}/api/v1/interview-access/status`,{credentials:"include",cache:"no-store"});
  if(!response.ok)throw new Error("Interview access is unavailable or outside the join window.");
}
