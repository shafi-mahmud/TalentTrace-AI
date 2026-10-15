import {createElement as h} from 'react';
import type {KeyboardEvent,FocusEvent} from 'react';

export interface AccountMenuProps {
  email:string;
  busy:boolean;
  error:string;
  onSignOut:()=>void;
}

// Native disclosure provides keyboard activation without pretending to be an ARIA menu.
// Authentication and sign-out state remain owned by RecruiterSignIn.
export default function RecruiterAccountMenu({email,busy,error,onSignOut}:AccountMenuProps) {
  return h('details',{className:'account-menu',
    onKeyDown:(event:KeyboardEvent<HTMLDetailsElement>)=>{
      if(event.key==='Escape') {
        event.currentTarget.open=false;
        event.currentTarget.querySelector('summary')?.focus();
      }
    },
    onBlur:(event:FocusEvent<HTMLDetailsElement>)=>{
      if(!event.currentTarget.contains(event.relatedTarget))event.currentTarget.open=false;
    }},
    h('summary',{'aria-label':'Account menu'},
      h('span',{className:'account-avatar','aria-hidden':true},email.slice(0,1).toUpperCase()),
      h('span',{className:'account-label'},'Account'),
      h('span',{className:'account-chevron','aria-hidden':true},'⌄')),
    h('div',{className:'account-menu-panel'},
      h('p',{className:'account-menu-caption'},'Signed in as'),
      h('p',{className:'account-identity'},email),
      h('button',{type:'button',className:'button button-secondary',disabled:busy,onClick:onSignOut},
        busy?'Signing out…':'Sign out'),
      error && h('p',{role:'alert',className:'account-error'},error)));
}
