import {createElement as h,useEffect,useState} from 'react';
import {listAIProviders} from '../api/recruiterChat.ts';
import type {AIProvider} from '../api/recruiterChat.ts';
export default function ProviderSelection({value,consent,disabled,onChange,onConsent}:{value:string;consent:boolean;disabled:boolean;onChange:(v:string)=>void;onConsent:(v:boolean)=>void}) {
 const [options,setOptions]=useState<AIProvider[]>([]),[failed,setFailed]=useState(false);
 useEffect(()=>{let active=true;void listAIProviders().then(v=>{if(active)setOptions(v);}).catch(()=>{if(active)setFailed(true);});return()=>{active=false;};},[]);
 return h('div',{className:'jd-provider'},
  h('label',null,'JD AI',h('select',{value,disabled:disabled||!options.length,onChange:(e:any)=>onChange(e.target.value)},
   h('option',{value:''},failed?'AI options unavailable':'Choose AI'),...options.map(p=>h('option',{key:p.id,value:p.id,disabled:!p.available},p.label+(p.available?'':' — unavailable'))))),
  value==='groq'&&h('label',null,h('input',{type:'checkbox',checked:consent,disabled,onChange:(e:any)=>onConsent(e.target.checked)}),'Send JD conversation and policy context to Groq.'),
  h('small',null,'JD only; CV screening settings are unchanged.'));
}
