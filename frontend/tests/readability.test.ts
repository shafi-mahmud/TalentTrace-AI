import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {EmptyConversation,RecruiterChatPage,ChatMessageView} from '../src/components/chatPresentation.ts';
import {SavedInterviews} from '../src/components/InterviewScheduling.ts';
import type {Interview} from '../src/api/interviews';

test('empty chat provides a short prompt with no generation or publication action',()=>{
 const html=renderToStaticMarkup(h(EmptyConversation));
 assert.match(html,/What role are you hiring for/);assert.match(html,/required skills/);
 assert.doesNotMatch(html,/button|iframe|textarea/);
});
test('policy implementation details are disclosed without losing the named source',()=>{
 const html=renderToStaticMarkup(h(RecruiterChatPage,{children:'Conversation'}));
 assert.match(html,/Synthetic Demo Company Policy/);
 assert.match(html,/<details[^>]*><summary>How it works/);
 assert.match(html,/Review generated content and its policy citations before publishing/);
});
test('message roles and processing errors remain distinct and visible',()=>{
 const html=renderToStaticMarkup(h(ChatMessageView,{message:{role:'recruiter',text:'Synthetic Python role',sendState:'failed',sendError:'Try later',retryAvailable:true},onRetry:()=>{}}));
 assert.match(html,/chat-recruiter/);assert.match(html,/>You</);assert.match(html,/role="alert"/);
 assert.match(html,/Retry message/);assert.match(html,/Your text remains in the composer/);
});
test('saved booking summary retains timezone, historical warning and accessible details',()=>{
 const id='00000000-0000-4000-8000-000000000001';
 const row:Interview={id,job_id:id,job_reference:'TT-JOB-0000000000000001',batch_id:id,upload_id:id,criteria_revision:2,scoring_version:'f2-coverage-v1',scheduled_at:'2026-10-20T05:00:00Z',timezone:'Asia/Dhaka',duration_minutes:60,unscored_confirmed:true,status:'scheduled'};
 const html=renderToStaticMarkup(h(SavedInterviews,{rows:[row],criteriaRevision:3,onOpenInterview:()=>{}}));
 assert.match(html,/Asia\/Dhaka/);assert.match(html,/60 minutes/);assert.match(html,/historical/);
 assert.match(html,/Unscored selection confirmed/);assert.match(html,/<summary>Booking details/);
 assert.match(html,/UTC: 2026-10-20T05:00:00.000Z/);assert.doesNotMatch(html,/Open interview/);
});
