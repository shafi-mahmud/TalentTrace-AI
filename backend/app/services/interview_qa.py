"""Conservative dialogue segmentation; no semantic answers are invented."""
import re
from typing import Literal
from uuid import UUID, uuid5
from pydantic import Field
from app.services.evaluation_input import Contract, EvaluationInput, EvaluationInputError


class QAPair(Contract):
    id: UUID
    question: str = Field(repr=False)
    answer: str = Field(repr=False)
    question_turns: tuple[UUID, ...]
    answer_turns: tuple[UUID, ...]
    capture_id: UUID
    start_ms: int
    end_ms: int
    status: Literal['answered','unanswered','uncertain']
    warnings: tuple[str, ...]
    question_role: Literal['recruiter'] = 'recruiter'
    answer_role: Literal['candidate'] = 'candidate'


def is_question(text):
    return '?' in text or bool(re.match(
        r'^(what|why|how|when|where|which|who|can you|could you|would you|do you|did you|have you|tell me|explain|describe)\b',
        text.strip(),re.I))


def is_connection_check(text):
    # Exact administrative phrases only; technical questions about audio remain.
    return bool(re.fullmatch(r'(can|could) you (hear|see) me(?: (?:clearly|now|okay|ok))?[?.!]*',text.strip(),re.I))


def pair_transcript(source: EvaluationInput) -> tuple[QAPair, ...]:
    pairs, question, answers, warnings = [], None, [], []
    def flush():
        if question is None:return
        pairs.append(QAPair(id=uuid5(source.interview_id,str(question.id)),
            question=question.text,answer='\n'.join(t.text for t in answers),
            question_turns=(question.id,),answer_turns=tuple(t.id for t in answers),
            capture_id=question.session_id,start_ms=question.start_ms,
            end_ms=max([question.end_ms]+[t.end_ms for t in answers]),
            status='uncertain' if warnings else 'answered' if answers else 'unanswered',
            warnings=tuple(dict.fromkeys(warnings))))
    for turn in source.turns:
        if question is not None and turn.session_id != question.session_id:
            warnings.append('capture_boundary_no_association');flush();question=None;answers=[];warnings=[]
        if turn.role=='recruiter' and is_connection_check(turn.text):
            if question is not None:
                warnings.append('connection_check_boundary_requires_review');flush()
            question=None;answers=[];warnings=[]
        elif turn.role=='recruiter' and is_question(turn.text):
            pending_without_answer=question is not None and not answers
            flush();question=turn;answers=[];warnings=[]
            if pending_without_answer:warnings.append('preceding_unanswered_question_requires_review')
            if turn.text.count('?')>1:warnings.append('multipart_question_requires_review')
        elif question is not None and turn.role=='candidate':
            if is_question(turn.text):
                warnings.append('candidate_clarification_not_assumed_answer')
            else:answers.append(turn)
        elif question is not None:
            warnings.append('interviewer_interruption_or_context_requires_review')
    flush()
    validate_pairs(source,tuple(pairs))
    return tuple(pairs)


def validate_pairs(source, pairs):
    turns={t.id:t for t in source.turns};used=set();ids=set()
    for pair in pairs:
        if pair.id in ids:raise EvaluationInputError('qa_duplicate_identity')
        ids.add(pair.id)
        for refs,text,role in [(pair.question_turns,pair.question,'recruiter'),(pair.answer_turns,pair.answer,'candidate')]:
            if len(refs)!=len(set(refs)):raise EvaluationInputError('qa_duplicate_identity')
            if any(ref not in turns or turns[ref].role!=role or turns[ref].session_id!=pair.capture_id or ref in used for ref in refs):
                raise EvaluationInputError('qa_source_mismatch')
            if '\n'.join(turns[ref].text for ref in refs)!=text:
                raise EvaluationInputError('qa_quote_not_in_source')
            used.update(refs)
        if not pair.question_turns or pair.status=='answered' and not pair.answer_turns:
            raise EvaluationInputError('qa_evidence_missing')

