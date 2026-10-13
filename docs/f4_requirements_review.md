# F4 model decision and requirements review - 13 October 2026

## Provisional architecture decision: retain local tiny.en

**Decision, owner-approved:** retain deployed tiny.en, CPU/int8, greedy decoding,
fixed four-second chunks and the 120-second default. The development-only extended
configuration remains bounded at 300 seconds. No pause-aware integration, provider
switch or model replacement is approved. This inline decision follows the existing
technical-document convention; no separate ADR directory was found.

**Verified offline comparison:** twelve fixed synthetic English sentences, slow,
default and fast offline TTS, identical PCM per comparison, two concurrent workers.
Systran base.en was downloaded outside Git from a pinned revision under its declared
MIT license. Tiny/base WER was 30.70/20.18%, 14.91/20.18%, and 14.91/14.91%.
Exact technical-term metric was 6/7, 9/9 and 8/9 out of 11. Base mean decoding
1.86-2.15 seconds versus tiny 0.85-1.07 seconds. These are synthetic findings.

**Verified physical read-aloud comparison:** both models received the same accepted
75.3-second microphone PCM, 753 frames, 19 chunks per worker. No audio was retained.

| Metric | tiny.en | base.en |
| --- | --- | --- |
| Script-based WER | 35.09% | 33.33% |
| Technical-term metric | 3/11 | 4/11 |
| Decode mean / p95 / maximum | 1.022 / 1.405 / 1.985 s | 1.722 / 1.906 / 1.921 s |
| Two-worker processing/audio-duration ratio | 0.259 | 0.435 |
| Estimated caption latency mean / p95 | 4.985 / 5.405 s | 5.685 / 5.906 s |
| Peak benchmark RAM | 397.8 MiB | 532.1 MiB |

Base improved script-based WER by only 1.76 percentage points, with about 68% more
mean decoding time. Neither simulated queue exceeded four seconds in this sample.
That does not establish worst-case live safety. Tiny is retained for lower cost in
CPU/latency, not because its natural-speech accuracy is satisfactory. Captions are
**unverified text until reviewed**, not candidate-assessment evidence by default.

## Measurement audit and limitations

- WER uses lowercase ASCII alphanumeric tokens and Levenshtein edit distance.
  Punctuation/case are ignored; acronym spacing, hyphens, numerals and spoken forms
  are not canonicalized. FastAPI versus "Fast API" can count as errors. No scores
  are retroactively recalculated because recognized text/audio has been discarded.
- The reference is the requested twelve-sentence script, not a human-verified
  transcript of what was actually uttered. Omitted, repeated or changed words can
  inflate apparent ASR error. Whole-session alignment cannot localize errors.
- Technical-term counting used substring presence, not exact token boundaries;
  it can overcount (for example, Python inside pythonic) and undercount acronym
  variants. Treat the reported figures as an approximate diagnostic metric.
- Four-second cuts are identical for both models, with no overlap. All accepted
  samples are covered once, including the final 3.3-second chunk. Boundary cuts
  can harm recognition. A sub-100-ms worklet tail or late frames at capture cutoff
  are outside the accepted PCM, so original utterance completeness is not proven.
- The offline harness flushes its final partial chunk; the live caption service
  cancels pending tails on stop/withdrawal. Offline accuracy is not directly
  equivalent to a live full-interview transcript.
- Two workers decoded duplicate copies of one speaker's input. This establishes
  concurrent decoding measurements, not independent speakers or overlapping-room
  performance. Queue/latency replay assumes ideal ingress and omits WebSocket,
  microphone and browser delays. CPU/RAM are sampled and can miss brief peaks.
- Four offline measurement tests passed for normalization, acronym differences,
  substring-count bias and final-tail conservation. They make no new ASR claims.

## Evidence sources and requirements status

The official BID, trainer clarification document, WBS and SRS were **not available**
in the inspected repository/root/docs or original worktree docs. README links to
`docs/wbs.md` and `docs/clarifications.md` do not establish their existence.
Obtain those authoritative artifacts before claiming complete F4 compliance or
assigning new WBS IDs. No trainer-authored requirements were modified.

Available approved architecture references:

- System Design v2.1: separate microphone STT side-channel, role streams, Google
  streaming STT and finalized turns for later Co-Pilot/evaluation. The owner has
  since explicitly required free local STT and accepted LiveKit transport.
- LangGraph Workflows v1.1: final STT turns enter one persistent interview Co-Pilot
  thread, private to the interviewer. This is documented, not implemented.
- Database Design v1.3: planned TranscriptTurn linked to InterviewSession, sequence,
  speaker, started_at, ended_at and text; final STT only, no raw audio/video.
  No TranscriptTurn ORM/table/API currently implements that planned entity.

| Area | Actual state | Missing / planned |
| --- | --- | --- |
| Duration | Implemented 120-second default, synthetic development limit up to 300; physical sessions reached 120 and 300.01-second caps | Authorized configured interview duration (roughly 10-30 minutes), sustained physical resource/gap verification |
| Timestamps | Implemented segment start/end relative to caption-session start, derived from frame receipt times | Stable interview-wide timeline across reconnects; speech/word alignment; explicit gap/partial-tail accounting |
| Speaker attribution | Implemented authenticated recruiter/candidate stream labels | Identity of actual speaker within shared/overlapping microphone audio is not proven; no diarization |
| Accuracy/review | Physical read-aloud comparison and user-observed captions | Reliable natural-speech accuracy, human correction/review UI and explicit unverified/reviewed state |
| Persistence | Captions transient, last 30 visible, cleared on stop; no raw audio persistence | Approved transcript storage, access, retention/deletion, review provenance and migration/API |
| Consent/privacy | Both-party server gate, withdrawal, owner/invitation authorization, deadlines, mute forwarding and bounded buffers implemented/tested | Production consent/retention governance, cross-device verification and longer-interview recovery policies |
| F5 readiness | Existing copilot package is an empty placeholder; no finalized-turn integration | Reviewed turn contract, stable timeline/provenance, interview thread integration and explicit human safeguards |

Five-minute numeric diagnostics establish sustained processing, not transcription
accuracy, lossless final-tail completion or independently verified video continuity.

## Recommended next increment - transient caption review and gap disclosure

Do not increase duration or build automatic evaluation yet. Add the smallest
owner-protected, in-memory review mode for a bounded synthetic caption session:

1. Label every generated segment Unverified; retain role, original text, sequence
   and timing while the authorized review session is active. Corrections remain
   separate from original ASR text; never silently overwrite provenance.
2. Allow explicit recruiter review/correction and a Reviewed marker, with clear
   disclosure/consent for this temporary review purpose. Preserve a bounded review
   list and explicitly disclose overflow, missing intervals and canceled tails.
3. Withdrawal, expiry and disconnect must cancel processing and clear transient
   review state under the existing privacy boundary. No database/export/F5 handoff
   in this increment. Confirm the desired post-call review lifetime before changing
   current stop-clears-everything behavior.

Acceptance/tests: no automatic reviewed status; safe text rendering; authorized
review only; original/corrected provenance; stable IDs; explicit gap notices;
bounded memory; duplicate/stale callbacks; expiry/withdrawal cleanup; no F5/provider
calls or transcript writes; existing media and caption behavior preserved.

Persistence, full-duration transcription and F5 integration follow separately after
official requirements, retention and stop/disconnect review policy are confirmed.
