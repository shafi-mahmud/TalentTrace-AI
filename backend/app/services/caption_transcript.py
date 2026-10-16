"""Trusted local recognizer adapter. Never accepts browser-supplied text."""
from datetime import datetime, timezone
from uuid import uuid5
from sqlalchemy import select
from app.db.models.interview_transcript import InterviewTranscriptSession
from app.schemas.interview_transcript import FinalTranscriptEvent
from app.services.interview_transcripts import transaction, TranscriptError


class CaptionTranscript:
    def __init__(self, runtime, interview_id):
        self.runtime, self.interview_id = runtime, interview_id
        self.capture = None
        self.owner = None
        self.started_at = None
        self.offset_ms = 0
        self.seen = set()
        self.acks = set()
        self.expected = 0
        self.acknowledged = 0
        self.failed = False
        self.uncertain = False
        self.finalizing = False
        self.grace_until = None

    async def start(self):
        entry = self.runtime.coordinator._entries.get(self.interview_id)
        if entry is None or entry.status != 'authorized_session_no_transcript':
            return
        try:
            async with transaction(self.runtime.storage.factory) as db:
                await self.runtime.storage._owned(db, entry.owner, self.interview_id, current=True)
                capture = await db.get(InterviewTranscriptSession, entry.capture_id)
                if capture is None or capture.status != 'active':
                    return
                self.capture, self.owner, self.started_at = capture.id, entry.owner, capture.started_at
                self.offset_ms = max(0, int((self.runtime.storage.clock()-capture.started_at).total_seconds()*1000))
        except TranscriptError:
            self.failed = True

    async def begin_finish(self):
        if self.capture is None or self.failed:
            return
        try:
            self.grace_until = await self.runtime.storage.begin_finalization(self.owner, self.capture)
            self.finalizing = True
        except TranscriptError:
            self.failed = True

    async def caption(self, event):
        if self.capture is None or self.failed:
            return
        self.seen.add(event['sequence'])
        self.expected = len(self.seen)
        try:
            value = FinalTranscriptEvent(id=uuid5(self.capture, str(event['sequence'])), session_id=self.capture,
                sequence=event['sequence'],role=event['role'],final=True,text=event['text'],
                start_ms=self.offset_ms+round(event['start']*1000),end_ms=self.offset_ms+round(event['end']*1000))
            await self.runtime.storage.append_final(self.owner,value,finalizing=self.finalizing)
            self.acks.add(event['sequence'])
            self.acknowledged = len(self.acks)
        except (TranscriptError, ValueError) as error:
            self.failed = True
            self.uncertain = isinstance(error,TranscriptError) and error.outcome_uncertain
        # There is no retained text queue or automatic retry after failure.

    async def finish(self, summary):
        if self.capture is None:
            return {'kind':'storage','status':'disabled','committed_turns':0}
        evidence = {'audio_outcome':summary.get('outcome','failed'),
            'expected_turns':self.expected,'acknowledged_turns':self.acknowledged,
            'accepted_samples':{role:v['accepted_samples'] for role,v in summary['roles'].items()},
            'processed_samples':{role:v['processed_samples'] for role,v in summary['roles'].items()},
            'scope':'accepted_audio_only','commit_uncertain':self.uncertain}
        complete = not self.failed and evidence['audio_outcome']=='drained' and self.expected==self.acknowledged
        try:
            row = await self.runtime.storage.finish_session(self.owner,self.capture,
                completed=complete,persistence_failed=self.failed,evidence=evidence)
            status = 'unconfirmed' if self.uncertain else ('saved' if row.status=='completed' and row.persistence_outcome=='saved' else 'incomplete')
        except TranscriptError:
            status = 'unconfirmed'
        return {'kind':'storage','status':status,'committed_turns':self.acknowledged}
