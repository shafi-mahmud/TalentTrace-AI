# Innovation Feature: Dynamic Interviewer Co-Pilot

Release documentation rationale. The existing filename is retained for link
compatibility. Physical F11 end-to-end acceptance remains pending.

## Rationale

Interviewers must listen, relate answers to job requirements and decide what to ask next at the same time. A static question list cannot respond to the conversation, while post-interview evaluation arrives too late to help collect missing evidence. The Dynamic Interviewer Co-Pilot addresses this evidence-collection problem by offering a provisional, context-linked next question during the interview.

Its distinctive functionality is prospective assistance rather than another candidate score. The assistant can invite an example after a relevant but limited answer or suggest exploring an approved requirement that has not been discussed. Suggestions remain private to the interviewer, who may ignore them. Silence, unclear recognition and missing discussion are not treated as evidence of incompetence. F5 evaluates recorded answers after the interview; F10 retrospectively assesses interview quality. F3 supplies communication and F4 supplies transcription. F11 instead intervenes while evidence can still be collected, without making a hiring judgment.

LangGraph represents the bounded decision process explicitly: validate context, assemble dialogue, track exploration, select a follow-up and validate the output. Simpler deterministic functions were a viable alternative. The graph was selected to make state, early exits and abstention paths explicit within the existing orchestration architecture. LangGraph itself is not the innovation; the contextual intervention and its integration are the proposed value. This bounded design prioritizes explainability and privacy over unrestricted model-generated advice.

F4 supplies recognized caption events through an internal adapter after authenticated participant processing. Events carry speaker, sequence, timing and caption-run identity. Browser-submitted transcript text is not an accepted source. A fresh assistant run binds to that caption run, and each participant must independently consent to F11 processing. Caption consent and optional storage consent do not substitute for assistant consent. Candidate-facing delivery excludes suggestions. Withdrawal clears transient context and suggestions, while generation and source checks fence stale work.

The implementation is deterministic and model-free. Co-pilot processing requires no external inference and uses bounded in-memory state without persistent co-pilot transcripts. The trade-off is limited language understanding: lexical associations and conservative dialogue patterns can miss paraphrases or abstain on fragmented speech. It does not establish technical correctness or comprehensive requirement coverage. Local recognition accuracy and the 120-second run limit constrain the demonstration.

Recorded automated synthetic integration tests exercise the trusted event hook, authorization, abstention and isolation. Physical speech-to-suggestion acceptance remains pending; those tests do not prove a successful microphone demonstration. Future improvements include measured language coverage and sustained-session behavior, with separate privacy review and continued abstention when evidence is uncertain.

## Authorship, assistance and requirement boundaries

Codex AI assisted preparation and editing of this rationale and the associated
implementation work recorded in this development session. This document does not
claim unaided invention, independently verified originality, trainer approval or
satisfaction of BID independent-design requirements.

The official BID, cover version 1.0, p.16, requires the trainee's own idea (C1),
independent design/implementation without trainer specification (C4), a working
feature (C5), README documentation (C7) and presentation (C8). These requirements
remain applicable; AI-assistance disclosure does not itself establish compliance.
No explicit AI-assistance disclosure format or additional trainer authorship policy
was located in the inspected BID/project documents. Any separately supplied BJIT
policy must also be followed; no permission to waive C1/C4 is inferred here.
