import {createElement as h,useState} from 'react';
import type {ChatMessage,AutomaticDestination} from '../types/recruiterChat';

// Deliberately narrow local command: never sends a publish instruction to the LLM.
export function isPublishingCommand(text:string) {
  return /^(?:\/publish|publish(?: this job)?)(?: to (?:discord|telegram|linkedin|other)(?:\s*(?:,|and)\s*(?:discord|telegram|linkedin|other))*)?[.!]?$/i.test(text.trim());
}
export function manualPublicationText(message:ChatMessage):string {
  const d=message.jobDescriptionResult?.job_description;
  if(!d||!message.draftId||!message.jobReference)return '';
  const c=message.publishingContext;
  return [d.title,`Job Reference: ${message.jobReference}`,c?.location?`Location: ${c.location}`:'',
    c?.employment_type?`Employment: ${c.employment_type.replaceAll('_',' ')}`:'',
    c?.work_arrangement?`Work arrangement: ${c.work_arrangement.replaceAll('_',' ')}`:'',d.summary,
    ...([['Responsibilities',d.responsibilities],['Required skills',d.required_skills],['Preferred skills',d.preferred_skills],['Qualifications',d.qualifications]] as const)
      .filter(([,items])=>items.length).map(([label,items])=>`${label}\n${items.map(t=>`• ${t}`).join('\n')}`)].filter(Boolean).join('\n\n');
}
export default function PublishingReview({message,busy,onPublish,onClose}:{message:ChatMessage;busy:boolean;onPublish:(destinations:AutomaticDestination[])=>Promise<void>;onClose:()=>void}) {
 const [destinations,setDestinations]=useState<string[]>([]),[reviewed,setReviewed]=useState(false),[confirmed,setConfirmed]=useState(false);
 const [copied,setCopied]=useState<string>(''),[copyError,setCopyError]=useState(false);
 const content=manualPublicationText(message);
 const resultDestinations=confirmed?destinations:(["discord","telegram"] as AutomaticDestination[]).filter(attempted);
 function state(destination:AutomaticDestination){return message.publications?.[destination]??(destination==='discord'?message.publication:undefined);}
 function attempted(destination:AutomaticDestination){const s=state(destination);return !!s&&s.status!=='idle';}
 function receipt(destination:AutomaticDestination){const s=state(destination),label=destination==='discord'?'Discord':'Telegram';return s?.status==='success'?`${label}: published · ${s.result.external_id}`:s?.status==='failed'?`${label}: ${s.message}`:`${label}: awaiting confirmation`;}
 async function confirm(){if(!reviewed||!destinations.length||confirmed||busy)return;setConfirmed(true);await onPublish(destinations.filter((d):d is AutomaticDestination=>d==='discord'||d==='telegram'));}
 async function copy(destination:string){try{await navigator.clipboard.writeText(content);setCopied(destination);setCopyError(false);}catch{setCopyError(true);}}
 return h('section',{className:'card publishing-review','aria-label':'Review job publishing'},
  h('h3',null,'Review publishing'),h('p',null,message.jobReference??'Select a saved job.'),
  !content?h('p',{role:'status'},'Open a saved job draft to publish.'):h('div',null,
   h('label',null,'Job content',h('textarea',{readOnly:true,value:content,rows:8})),
   h('fieldset',{disabled:busy||confirmed},h('legend',null,'Destinations'),
    ...(['discord','telegram','linkedin','other'] as const).map(destination=>h('label',{key:destination},
     h('input',{type:'checkbox',checked:destinations.includes(destination),disabled:(destination==='discord'||destination==='telegram')&&attempted(destination),onChange:()=>{setReviewed(false);setDestinations(destinations.includes(destination)?destinations.filter(d=>d!==destination):[...destinations,destination]);}}),
     destination==='discord'?'Discord — automatic':destination==='telegram'?'Telegram — automatic (if configured)':destination==='linkedin'?'LinkedIn — manual':'Other platform — manual'))),
   h('label',null,h('input',{type:'checkbox',checked:reviewed,disabled:busy||confirmed,onChange:()=>setReviewed(!reviewed)}),'I reviewed the content and selected destinations.'),
   h('button',{type:'button',className:'button button-primary',disabled:busy||confirmed||!reviewed||!destinations.length,onClick:()=>void confirm()},'Confirm destinations'),
   !!resultDestinations.length&&h('ul',{'aria-label':'Destination results'},...resultDestinations.map(destination=>h('li',{key:destination},
    (destination==='discord'||destination==='telegram')?receipt(destination):
    h('div',null,`${destination==='linkedin'?'LinkedIn':'Other platform'}: manual action required`,
     h('button',{type:'button',className:'button button-secondary',onClick:()=>void copy(destination)},'Copy job content'),
     copied===destination&&h('span',{role:'status'},'Copied — not posted'))))),
   copyError&&h('p',{role:'alert'},'Copy unavailable. Select the preview text manually.')),
  h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:onClose},'Close preview'));
}
