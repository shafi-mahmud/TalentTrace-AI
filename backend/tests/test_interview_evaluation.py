import asyncio
from uuid import uuid4
import pytest
from app.agents.evaluation.workflow import (InterviewEvaluationWorkflow,ModelAssessment,
    AssessmentError,validate_assessment)
from app.services.interview_mapping import SyntheticTechnicalRetriever
from app.services.interview_qa import pair_transcript
from test_interview_qa import dialogue


def assessment(pairs,unsupported=False):
    return ModelAssessment.model_validate({'answers':[{'qa_id':p.id,
        'dimensions':[{'dimension':d,'status':'uncertain','justification':'Synthetic test interpretation; review required.',
            'evidence':[{'turn_id':p.answer_turns[0],'quote':'invented'}] if unsupported and p.answer_turns else []}
            for d in ['relevance','technical_accuracy','completeness','articulation']],
        'technical_citations':[],'follow_up':'Ask for a concrete example.'} for p in pairs]})


class FakeProvider:
    name='mock';model='offline-test-only'
    def __init__(self,invalid=False,fail=False):self.calls=0;self.invalid=invalid;self.fail=fail
    async def assess(self,source,pairs,mappings,references,repair=False,repair_error=None):
        self.calls+=1
        if self.fail:raise AssessmentError('evaluation_provider_unavailable')
        return assessment(pairs,self.invalid and not repair)


def test_real_graph_nodes_and_controlled_grounding_repair():
    source=dialogue([('recruiter','What is Python?'),('candidate','A programming language.')])
    provider=FakeProvider(invalid=True)
    graph=InterviewEvaluationWorkflow(provider,SyntheticTechnicalRetriever())
    result=asyncio.run(graph.run(source))
    assert result['validated'] and result['pairs'] and result['mappings'] and result['references']
    assert provider.calls==2
    assert set(graph.graph.nodes)>={'pair_questions','map_requirements','retrieve_technical_references','assess_answers','validate_evidence'}


def test_provider_failure_is_processing_failure_not_candidate_exclusion():
    provider=FakeProvider(fail=True)
    with pytest.raises(AssessmentError,match='evaluation_provider_unavailable'):
        asyncio.run(InterviewEvaluationWorkflow(provider,SyntheticTechnicalRetriever()).run(
            dialogue([('recruiter','What is Python?'),('candidate','A language.')])) )
    assert provider.calls==1


@pytest.mark.parametrize('defect',['quote','wrong_question','duplicate_dimension','unsupported_accuracy','unanswered_concern','technical_citation'])
def test_untrusted_model_output_is_grounded(defect):
    source=dialogue([('recruiter','What is Python?'),('candidate','A language.'),('recruiter','Explain tuples?')])
    pairs=pair_transcript(source);value=assessment(pairs).model_dump(mode='json')
    answer=value['answers'][0]
    if defect=='quote':answer['dimensions'][0]['evidence']=[{'turn_id':str(pairs[0].answer_turns[0]),'quote':'hallucinated quote'}]
    elif defect=='wrong_question':answer['qa_id']=str(uuid4())
    elif defect=='duplicate_dimension':answer['dimensions'][1]['dimension']='relevance'
    elif defect=='unsupported_accuracy':
        answer['dimensions'][1].update(status='supported',evidence=[{'turn_id':str(pairs[0].answer_turns[0]),'quote':'A language.'}])
    elif defect=='unanswered_concern':value['answers'][1]['dimensions'][0]['status']='concern'
    elif defect=='technical_citation':answer['technical_citations']=[{'reference_id':'invented','quote':'unsupported'}]
    with pytest.raises(AssessmentError):validate_assessment(source,pairs,(),ModelAssessment.model_validate(value))


def test_external_trace_is_blocked(monkeypatch):
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    with pytest.raises(AssessmentError,match='evaluation_external_tracing_not_allowed'):
        asyncio.run(InterviewEvaluationWorkflow(FakeProvider(),SyntheticTechnicalRetriever()).run(
            dialogue([('recruiter','What is Python?'),('candidate','A language.')])) )


def test_groq_adapter_strict_output_and_no_network_retry():
    from types import SimpleNamespace as N
    from app.integrations.llm.interview_evaluation import GroqInterviewAssessment
    source=dialogue([('recruiter','What is Python?'),('candidate','A language.')]);pairs=pair_transcript(source)
    calls=[]
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['max_retries']==0
            self.chat=N(completions=self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def create(self,**kwargs):
            calls.append(kwargs)
            return N(choices=[N(message=N(content=assessment(pairs).model_dump_json()))])
    result=asyncio.run(GroqInterviewAssessment('synthetic-test-secret','configured-model',Client).assess(source,pairs,(),()))
    assert result.answers and len(calls)==1 and calls[0]['temperature']==0


@pytest.mark.parametrize('failure',['invalid_json','timeout','rate_limit'])
def test_groq_failures_are_sanitized_and_never_automatically_retried(failure):
    import httpx
    from groq import APITimeoutError,RateLimitError
    from types import SimpleNamespace as N
    from app.integrations.llm.interview_evaluation import GroqInterviewAssessment
    source=dialogue([('recruiter','What is Python?'),('candidate','A language.')]);calls=[]
    class Client:
        def __init__(self,**kwargs):self.chat=N(completions=self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def create(self,**kwargs):
            calls.append(1)
            request=httpx.Request('POST','https://synthetic.invalid')
            if failure=='timeout':raise APITimeoutError(request=request)
            if failure=='rate_limit':raise RateLimitError('private provider text',response=httpx.Response(429,request=request),body=None)
            return N(choices=[N(message=N(content='private invalid provider output'))])
    with pytest.raises(AssessmentError) as error:
        asyncio.run(GroqInterviewAssessment('synthetic-secret','configured',Client).assess(source,pair_transcript(source),(),()))
    assert 'private' not in str(error.value) and len(calls)==1

def test_repair_rule_is_specific_and_bounded():
    feedback=[]
    class InvalidProvider(FakeProvider):
        async def assess(self,source,pairs,mappings,references,repair=False,repair_error=None):
            feedback.append((repair,repair_error))
            return assessment(pairs,unsupported=True)
    with pytest.raises(AssessmentError,match='evaluation_quote_not_in_source'):
        asyncio.run(InterviewEvaluationWorkflow(InvalidProvider(),SyntheticTechnicalRetriever()).run(
            dialogue([('recruiter','What is Python?'),('candidate','A language.')])) )
    assert feedback==[(False,None),(True,'evaluation_quote_not_in_source')]


def test_uncertain_asr_pair_can_abstain():
    source=dialogue([('recruiter','In Python.'),('candidate','Bye.'),
        ('recruiter','are lists mutable.'),('candidate','on lists are mutable. You can append new items.')])
    result=asyncio.run(InterviewEvaluationWorkflow(FakeProvider(),SyntheticTechnicalRetriever()).run(source))
    assert result['validated'] and len(result['pairs'])==1
    assert result['pairs'][0].status=='uncertain'
    assert all(d.status=='uncertain' for d in result['assessment'].answers[0].dimensions)


def test_unknown_validation_error_is_sanitized(monkeypatch):
    import app.agents.evaluation.workflow as module
    def invalid(*args):raise AssessmentError('private synthetic diagnostic text')
    monkeypatch.setattr(module,'validate_assessment',invalid)
    with pytest.raises(AssessmentError,match='evaluation_output_not_grounded'):
        asyncio.run(InterviewEvaluationWorkflow(FakeProvider(),SyntheticTechnicalRetriever()).run(
            dialogue([('recruiter','What is Python?'),('candidate','A language.')])) )


@pytest.mark.parametrize('feedback',['evaluation_quote_not_in_source','private synthetic diagnostic text'])
def test_adapter_sanitizes_repair_feedback(feedback):
    import json
    from types import SimpleNamespace as N
    from app.integrations.llm.interview_evaluation import GroqInterviewAssessment
    source=dialogue([('recruiter','What is Python?'),('candidate','A language.')]);pairs=pair_transcript(source)
    payloads=[]
    class Client:
        def __init__(self,**kwargs):self.chat=N(completions=self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def create(self,**kwargs):
            payloads.append(json.loads(kwargs['messages'][1]['content']))
            return N(choices=[N(message=N(content=assessment(pairs).model_dump_json()))])
    asyncio.run(GroqInterviewAssessment('synthetic-secret','configured',Client).assess(
        source,pairs,(),(),repair=True,repair_error=feedback))
    assert payloads[0]['failed_validation_rule']==(feedback if feedback.startswith('evaluation_') else None)
    assert 'private synthetic diagnostic text' not in json.dumps(payloads)
