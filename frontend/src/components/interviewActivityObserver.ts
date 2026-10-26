import type {Activity} from '../api/interviewAttention.ts';
export function activity(document:Document):Activity {
 return {visibility:document.visibilityState==='visible'?'visible':document.visibilityState==='hidden'?'hidden':'unsupported',
  fullscreen:document.fullscreenEnabled?document.fullscreenElement?'active':'inactive':'unsupported'};
}
// Only installed after explicit consent. Serialize sends and retain one latest update.
export function observeActivity(document:Document,send:(v:Activity)=>Promise<void>,failed:()=>void){
 let active=true,pending:Activity|null=null,sending=false;
 async function flush(){
  if(sending||!active)return;sending=true;
  try{while(active&&pending){const next=pending;pending=null;await send(next);}}
  catch{if(active){stop();failed();}}
  finally{sending=false;}
 }
 const changed=()=>{if(active){pending=activity(document);void flush();}};
 const timer=setInterval(changed,10000);
 function stop(){active=false;pending=null;clearInterval(timer);document.removeEventListener('visibilitychange',changed);document.removeEventListener('fullscreenchange',changed);}
 document.addEventListener('visibilitychange',changed);document.addEventListener('fullscreenchange',changed);changed();
 return stop;
}
