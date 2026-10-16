"""Literal requirement-topic coverage, deliberately separate from skill judgement."""
import re
from typing import Literal, Protocol
from uuid import UUID
from pydantic import Field
from app.services.evaluation_input import Contract
from app.services.interview_qa import validate_pairs


class RequirementMapping(Contract):
    criterion_id: str
    description: str = Field(repr=False)
    qa_ids: tuple[UUID, ...]
    turn_ids: tuple[UUID, ...]
    coverage: Literal['partial','not_evidenced','uncertain']
    explanation: str
    follow_up: str


def map_requirements(source,pairs):
    validate_pairs(source,pairs)
    ignored={'the','a','an','and','or','of','in','with','to','for','skill','skills','experience','knowledge','required','preferred'}
    result=[]
    for criterion in source.criteria:
        terms=set(re.findall(r'[a-z0-9+#]+',criterion.description.lower()))-ignored
        matches=[p for p in pairs if terms and terms.issubset(set(re.findall(r'[a-z0-9+#]+',(p.question+' '+p.answer).lower())))]
        uncertain=any(p.status=='uncertain' or re.search(r"\b(no|not|never|unsure|uncertain|cannot|can't|don't|haven't)\b",p.answer,re.I) for p in matches)
        status='uncertain' if uncertain else 'partial' if matches else 'not_evidenced'
        result.append(RequirementMapping(criterion_id=criterion.criterion_id,description=criterion.description,
            qa_ids=tuple(p.id for p in matches),turn_ids=tuple(dict.fromkeys(t for p in matches for t in p.question_turns+p.answer_turns)),
            coverage=status,explanation='Literal topic mentioned; competence is not established.' if matches else 'No literal topic match; semantic coverage remains unassessed, not lack of skill.',
            follow_up='Ask for a concrete example addressing this confirmed requirement.'))
    return tuple(result)


class TechnicalReference(Contract):
    id: str
    topic: str
    text: str = Field(repr=False)
    provenance: Literal['synthetic_demo','official_documentation_summary'] = 'synthetic_demo'
    source_title: str = ''
    document_id: str = ''
    location: str = ''
    url: str = ''
    version: str = ''
    retrieval_basis: str = 'synthetic_fixture'


class TechnicalRetriever(Protocol):
    async def retrieve(self,source,pairs) -> tuple[TechnicalReference, ...]: ...


class SyntheticTechnicalRetriever:
    """Tiny explicit demo corpus, not a production/vector Technical Knowledge RAG."""
    async def retrieve(self,source,pairs):
        text=' '.join(p.question+' '+p.answer for p in pairs).lower()
        facts=[('demo-python-list-v1','python','Python lists are ordered mutable collections; tuples are immutable.'),
            ('demo-sql-transaction-v1','transaction','A database transaction groups operations that commit together or roll back.'),
            ('demo-http-method-v1','http','HTTP GET is defined for retrieval; POST submits data for processing.')]
        return tuple(TechnicalReference(id=i,topic=topic,text=value) for i,topic,value in facts if topic in text)
