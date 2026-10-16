import type {ConsolidatedReport} from './consolidatedAssessment';

export interface PrintHost {
 mount(report:ConsolidatedReport,preparedAt:string):()=>void;
 print():void;
 afterPrint(callback:()=>void):()=>void;
 beforePrint(callback:()=>void):()=>void;
 expireAfter(milliseconds:number,callback:()=>void):()=>void;
 finished():void;
 now?:()=>number;
}

let activePrint=false;

/** Called only by the recruiter button. No storage, download, provider, or new API. */
export async function printAssessment(load:()=>Promise<ConsolidatedReport>,host:PrintHost,signal:AbortSignal){
 if(activePrint)throw new Error('Another report print is active.');
 activePrint=true;
 let releasePrint:(()=>void)|undefined;
 try{
 const now=host.now??Date.now;
 const report=await load();
 if(signal.aborted)throw new Error('Print context changed.');
 const deadline=report.interview.state==='available'?Date.parse(report.interview.retention_deadline!):Infinity;
 if((report.interview.state==='available'&&!Number.isFinite(deadline))||deadline<=now())throw new Error('Interview evidence expired.');
 let disposed=false;
 const releases:(()=>void)[]=[];
 const cleanup=()=>{if(disposed)return;disposed=true;activePrint=false;for(const release of releases)release();host.finished();};
 releasePrint=cleanup;
 try{
  releases.push(host.mount(report,new Date(now()).toISOString()));
  releases.push(host.afterPrint(cleanup));
  releases.push(host.beforePrint(()=>{if(deadline<=now()||signal.aborted)cleanup();}));
  releases.push(host.expireAfter(Math.min(deadline-now(),300000),cleanup));
  signal.addEventListener('abort',cleanup,{once:true});
  releases.push(()=>signal.removeEventListener('abort',cleanup));
  host.print(); // Browser controls printer, destination, filename, and cancellation.
  return cleanup;
 }catch(error){cleanup();throw error;}
 }catch(error){if(releasePrint)releasePrint();else activePrint=false;throw error;}
}
