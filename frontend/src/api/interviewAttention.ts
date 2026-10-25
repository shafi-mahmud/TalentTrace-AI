export type Activity={visibility:'visible'|'hidden'|'unsupported';fullscreen:'active'|'inactive'|'unsupported'};
const base=(import.meta.env?.VITE_API_BASE_URL??'').replace(/\/+$/,'');
async function request(path:string,body?:unknown){
 const r=await fetch(base+'/api/v1'+path,{method:body===undefined?'GET':'POST',credentials:'include',cache:'no-store',signal:AbortSignal.timeout(5000),
  headers:{'X-TalentTrace-Request':'1',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(!r.ok)throw Error('Status sharing unavailable.');return r.json();
}
export async function consent(){const v=await request('/interview-access/attention/consent',{version:'attention-v1',decision:'accept'});if(typeof v?.run_id!=='string'||!/^[a-f0-9-]{36}$/.test(v.run_id))throw Error('Status sharing unavailable.');return v.run_id as string;}
export async function send(run_id:string,value:Activity){await request('/interview-access/attention',{run_id,...value});}
export async function withdraw(run_id:string){await request('/interview-access/attention/withdraw',{run_id});}
export async function status(job:string,interview:string):Promise<Activity|null>{
 const v=await request(`/jobs/${encodeURIComponent(job)}/interviews/${encodeURIComponent(interview)}/attention`);
 if(v?.state==='not_shared'&&Object.keys(v).length===1)return null;
 if(v?.state!=='shared'||Object.keys(v).length!==3||!['visible','hidden','unsupported'].includes(v.visibility)||!['active','inactive','unsupported'].includes(v.fullscreen))throw Error('Status sharing unavailable.');
 return {visibility:v.visibility,fullscreen:v.fullscreen};
}
