import {createElement as h,useState} from 'react';

export async function copyJobReference(reference:string,write:(text:string)=>Promise<void>):Promise<string> {
  if(!/^TT-JOB-[A-F0-9]{16}$/.test(reference))return 'Job Reference unavailable.';
  try{await write(reference);return 'Job Reference copied.';}
  catch{return 'Copy unavailable. Select and copy the Job Reference shown above.';}
}

export default function SavedJobIdentity({jobReference,revision,internalId}:{jobReference?:string;revision?:number;internalId?:string}) {
  const [copyStatus,setCopyStatus]=useState('');
  if(!jobReference||!/^TT-JOB-[A-F0-9]{16}$/.test(jobReference)||revision===undefined||!Number.isInteger(revision)||revision<1)
    return h('p',{className:'helper-text'},'Saved job identity unavailable. Reload saved jobs before continuing.');
  return h('section',{className:'saved-job-identity','aria-label':'Saved job identity'},
    h('p',null,'Draft saved under Job Reference ',h('strong',null,jobReference),` · Revision ${revision}`),
    h('button',{type:'button',className:'button button-secondary',onClick:()=>void copyJobReference(jobReference,
      value=>navigator.clipboard.writeText(value)).then(setCopyStatus)},'Copy Job Reference'),
    h('p',{role:'status'},copyStatus),
    h('details',null,h('summary',null,'Internal job identifier'),h('p',null,'Internal UUID (not the Job Reference): ',internalId)));
}
