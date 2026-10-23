import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import RecruiterAccountMenu from '../src/components/RecruiterAccountMenu.ts';
import {WorkspaceNavigation} from '../src/components/cvIntakePresentation.ts';

const props={email:'synthetic@example.test',busy:false,error:'',onSignOut:()=>{}};
test('one cohesive header contains brand, navigation and right-hand account control',()=>{
 const html=renderToStaticMarkup(h(WorkspaceNavigation,{mode:'jd',onChange:()=>{},accountControls:h(RecruiterAccountMenu,props)}));
 assert.equal(html.split('<header').length-1,1);
 for(const text of ['TalentTrace','JD Assistant','Candidate Screening','Interview Scheduling','Account menu','Sign out'])assert.match(html,new RegExp(text));
 assert.match(html,/class="header-account"/);assert.doesNotMatch(html,/account-bar/);
 assert.match(html,/aria-pressed="true">JD Assistant/);
 assert.match(html,/<details class="account-menu"><summary aria-label="Account menu"/);
});
test('account identity is escaped and sign-out failure remains visible inside the disclosure',()=>{
 const html=renderToStaticMarkup(h(RecruiterAccountMenu,{...props,email:'<script>@example.test',error:'Sign-out was not confirmed.'}));
 assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
 assert.match(html,/role="alert"/);assert.match(html,/Sign-out was not confirmed/);
 assert.doesNotMatch(html,/role="menu"/); // Native disclosure, not a partial ARIA menu implementation.
});
test('sign-out callback is explicit, runs once per click, and is disabled while pending',()=>{
 let calls=0;
 const menu=RecruiterAccountMenu({...props,onSignOut:()=>{calls++;}});
 const panel=menu.props.children[1];
 const button=panel.props.children[2];
 assert.equal(calls,0);button.props.onClick();assert.equal(calls,1);
 const html=renderToStaticMarkup(h(RecruiterAccountMenu,{...props,busy:true}));
 assert.match(html,/<button[^>]*disabled=""[^>]*>Signing out/);
});
test('Escape closes account disclosure and restores summary focus',()=>{
 let focused=false;
 const currentTarget={open:true,querySelector:()=>({focus:()=>{focused=true;}})};
 const menu=RecruiterAccountMenu(props);
 menu.props.onKeyDown({key:'Escape',currentTarget});
 assert.equal(currentTarget.open,false);assert.equal(focused,true);
});
test('all recruiter navigation callbacks remain independent of account actions',()=>{
 const changes:string[]=[];
 const header=WorkspaceNavigation({mode:'cv',onChange:mode=>changes.push(mode),accountControls:h(RecruiterAccountMenu,props)});
 const nav=header.props.children.props.children[1];
 for(const button of nav.props.children)button.props.onClick();
 assert.deepEqual(changes,['home','jd','cv','scheduling']);
});
