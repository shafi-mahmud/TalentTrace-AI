import {createElement as h,useEffect,useRef,useState} from 'react';
import {listAIProviders} from '../api/recruiterChat.ts';
import type {AIProvider} from '../api/recruiterChat.ts';
export function defaultProvider(options:AIProvider[],value:string,explicitChoice=false,allowDefault=true):string {
 return !value&&!explicitChoice&&allowDefault&&options.some(p=>p.id==='groq'&&p.available)?'groq':'';
}
export default function ProviderSelection({value,consent,disabled,onChange,onConsent,scope="jd",allowDefault=true,locked=false}:{scope?:"jd"|"cv";value:string;consent:boolean;disabled:boolean;allowDefault?:boolean;locked?:boolean;onChange:(v:string)=>void;onConsent:(v:boolean)=>void}) {
 const [options,setOptions]=useState<AIProvider[]>([]),[failed,setFailed]=useState(false);
 const explicitChoice=useRef(false);
 useEffect(()=>{let active=true;void listAIProviders().then(v=>{if(active)setOptions(v);}).catch(()=>{if(active)setFailed(true);});return()=>{active=false;};},[]);
 useEffect(()=>{const next=defaultProvider(options,value,explicitChoice.current,allowDefault&&!disabled&&!locked);if(next)onChange(next);},[options,value,allowDefault,disabled,locked,onChange]);
 return h('div',{className:'jd-provider'},
  h('label',null,scope==='cv'?'CV AI':'JD AI',h('select',{'aria-label':scope==='cv'?'CV AI':'JD AI',value,disabled:disabled||locked||!options.length,onChange:(e:any)=>{explicitChoice.current=true;onChange(e.target.value);onConsent(false);}},
   h('option',{value:''},failed?'AI options unavailable':'Choose AI'),...options.map(p=>h('option',{key:p.id,value:p.id,disabled:!p.available},p.label+(p.available?'':' — unavailable'))))),
  value==='groq'&&h('label',null,h('input',{type:'checkbox',checked:consent,disabled,onChange:(e:any)=>onConsent(e.target.checked)}),scope==='cv'?'Send CV text and derived qualifications to Groq.':'Send JD conversation and policy context to Groq.'),
  (failed||options.length>0&&!options.some(p=>p.id==='groq'&&p.available))&&h('p',{role:'status'},'Groq is unavailable. Check provider configuration; no other model was selected automatically.'),
  locked&&h('small',null,'This conversation keeps its original AI provider. Start a new chat to change it.'),
  h('small',null,scope==='cv'?'Applies to profile extraction and screening.':'JD provider selection is separate from CV screening.'));
}
