"""Meaningful bounded graph; deterministic grounding surrounds model interpretation."""
import os
from typing import Literal, TypedDict, Protocol
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from langgraph.graph import StateGraph, START, END
from app.services.evaluation_input import EvaluationInput, EvaluationInputError, EvidenceQuote, validate_quotes
from app.services.interview_qa import pair_transcript, validate_pairs
from app.services.interview_mapping import map_requirements

RUBRIC_VERSION='interview-evidence-v1'


class AssessmentError(Exception):pass


class Output(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,hide_input_in_errors=True)


class Quotation(Output):
    turn_id:UUID
    quote:str=Field(min_length=1,max_length=1000,repr=False)


class TechnicalCitation(Output):
    reference_id:str=Field(min_length=1,max_length=100)
    quote:str=Field(min_length=1,max_length=1000,repr=False)


class Dimension(Output):
    dimension:Literal['relevance','technical_accuracy','completeness','articulation']
    status:Literal['supported','partial','concern','uncertain','not_assessed']
    justification:str=Field(min_length=1,max_length=800,repr=False)
    evidence:list[Quotation]=Field(max_length=8,repr=False)


class AnswerAssessment(Output):
    qa_id:UUID
    dimensions:list[Dimension]=Field(min_length=4,max_length=4)
    technical_citations:list[TechnicalCitation]=Field(max_length=5,repr=False)
    follow_up:str=Field(min_length=1,max_length=400)


class ModelAssessment(Output):
    answers:list[AnswerAssessment]=Field(min_length=1,max_length=50)


class AssessmentProvider(Protocol):
    name:str
    model:str
    async def assess(self,source,pairs,mappings,references,repair=False)->ModelAssessment: ...


def validate_assessment(source,pairs,references,result):
    validate_pairs(source,pairs)
    result=ModelAssessment.model_validate(result.model_dump())
    if len(result.answers)!=len(pairs) or {a.qa_id for a in result.answers}!={p.id for p in pairs}:
        raise AssessmentError('evaluation_question_identity_mismatch')
    refs={r.id:r for r in references}; by_id={p.id:p for p in pairs}
    for answer in result.answers:
        pair=by_id[answer.qa_id]
        if {d.dimension for d in answer.dimensions}!={'relevance','technical_accuracy','completeness','articulation'}:
            raise AssessmentError('evaluation_dimensions_incomplete')
        for citation in answer.technical_citations:
            if citation.reference_id not in refs or not citation.quote.strip() or citation.quote not in refs[citation.reference_id].text:
                raise AssessmentError('evaluation_technical_citation_invalid')
        for dimension in answer.dimensions:
            if not pair.answer_turns and dimension.status not in {'not_assessed','uncertain'}:
                raise AssessmentError('evaluation_unanswered_is_not_failure')
            if pair.status=='uncertain' and dimension.status=='supported':
                raise AssessmentError('evaluation_pairing_requires_review')
            if dimension.status not in {'not_assessed','uncertain'} and not dimension.evidence:
                raise AssessmentError('evaluation_evidence_missing')
            if dimension.evidence:
                try:validate_quotes(source,tuple(EvidenceQuote(turn_id=e.turn_id,quote=e.quote) for e in dimension.evidence))
                except EvaluationInputError:raise AssessmentError('evaluation_quote_not_in_source') from None
                if any(e.turn_id not in pair.question_turns+pair.answer_turns for e in dimension.evidence):
                    raise AssessmentError('evaluation_cross_question_evidence')
                if dimension.status not in {'not_assessed','uncertain'} and not any(e.turn_id in pair.answer_turns for e in dimension.evidence):
                    raise AssessmentError('evaluation_candidate_evidence_missing')
            if dimension.dimension=='technical_accuracy' and dimension.status not in {'uncertain','not_assessed'} and not answer.technical_citations:
                raise AssessmentError('evaluation_accuracy_reference_missing')
    return result


class State(TypedDict,total=False):
    source:EvaluationInput
    pairs:tuple
    mappings:tuple
    references:tuple
    assessment:ModelAssessment
    repair:bool
    validated:bool


class InterviewEvaluationWorkflow:
    def __init__(self,provider,retriever):
        self.provider,self.retriever=provider,retriever
        graph=StateGraph(State)
        graph.add_node('pair_questions',self.pair)
        graph.add_node('map_requirements',self.mapping)
        graph.add_node('retrieve_technical_references',self.retrieve)
        graph.add_node('assess_answers',self.assess)
        graph.add_node('validate_evidence',self.validate)
        graph.add_edge(START,'pair_questions');graph.add_edge('pair_questions','map_requirements')
        graph.add_edge('map_requirements','retrieve_technical_references')
        graph.add_edge('retrieve_technical_references','assess_answers')
        graph.add_edge('assess_answers','validate_evidence')
        graph.add_conditional_edges('validate_evidence',lambda s:'done' if s['validated'] else 'repair',{'done':END,'repair':'assess_answers'})
        self.graph=graph.compile(checkpointer=False)

    async def run(self,source):
        if any(os.environ.get(k,'').lower() in {'1','true'} for k in ('LANGSMITH_TRACING','LANGCHAIN_TRACING_V2')):
            raise AssessmentError('evaluation_external_tracing_not_allowed')
        return await self.graph.ainvoke({'source':source,'repair':False},{'recursion_limit':12,'callbacks':[]})

    async def pair(self,state):
        pairs=pair_transcript(state['source'])
        if not pairs or len(pairs)>50:raise AssessmentError('evaluation_questions_missing_or_unbounded')
        return {'pairs':pairs}

    async def mapping(self,state):return {'mappings':map_requirements(state['source'],state['pairs'])}
    async def retrieve(self,state):return {'references':await self.retriever.retrieve(state['source'],state['pairs'])}
    async def assess(self,state):
        return {'assessment':await self.provider.assess(state['source'],state['pairs'],state['mappings'],state['references'],state['repair'])}
    async def validate(self,state):
        try:validate_assessment(state['source'],state['pairs'],state['references'],state['assessment'])
        except (AssessmentError,ValidationError):
            if state['repair']:raise AssessmentError('evaluation_output_not_grounded') from None
            return {'validated':False,'repair':True}
        return {'validated':True}
