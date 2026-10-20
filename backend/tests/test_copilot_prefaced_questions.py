"""Exact provider recognition and conservative surface-grammar regressions; offline."""
import asyncio
import pytest
from app.agents.copilot import workflow
from app.schemas.interview_copilot import Requirement
from test_interview_copilot import binding,no_network,execute,update
from test_copilot_delivery import runtime,offline,consent
from test_copilot_live import ready,idle

QUESTION='In Python, our list mutable, explain how append changes a list and how indexing retrieves. An element.'
ANSWER='Python lists are mutable ordered sequences. The append method adds one item to the end of the existing list. Indexing starts at zero negative index such as minus one retrieves the last. Element.'


def test_exact_recognized_pair_keeps_text_and_source_references(binding):
    logic,result=execute(binding,[('recruiter',QUESTION),('candidate',ANSWER)])
    assert result.status=='suggested' and result.reason=='valid_suggestion'
    assert result.suggestions[0].criterion_id=='python'
    assert result.suggestions[0].kind=='example'
    assert [s.sequence for s in result.suggestions[0].sources]==[1,2]
    assert result.exploration[0].state=='response_observed'
    assert result.exploration[1].state=='not_observed'


@pytest.mark.parametrize('question',[
    'Explain Python lists','Describe Python lists.','What are Python lists?',
    'How do Python lists work','Tell me about Python lists','Can you explain Python lists',
    'Could you describe Python lists','Do you use Python lists','Are Python lists mutable',
    'In Python, explain lists','Regarding Python lists: describe mutability',
    'For Python lists. How does append work','With respect to Python lists, explain indexing',
    'Python lists?', QUESTION,
])
def test_direct_and_bounded_prefaces(question):
    assert workflow.is_question(question)


@pytest.mark.parametrize('question',[
    'Do not explain Python lists','Do not ever explain Python lists',"Don't explain Python lists",
    'In Python, never explain lists','In Python, avoid explaining lists',
    'In Python, our list mutable, do not explain append',
    '"Explain Python lists"','In Python, "explain lists"',
    "In Python, 'explain lists'",'She said explain Python lists',
    'In Python, she asked how lists work','According to the trainer, explain Python lists?',
    'The instruction says: explain Python lists','I know how Python lists work',
    'Python lists explain our design','In Python, I went shopping, explain lists',
    'In Python because we met yesterday, explain lists',
    'During lunch, explain Python lists','During lunch, explain Python lists?',
    'I went shopping, explain Python lists?','In Python, unrelated clause, explain lists',
    'In Python, our lists, the index, explain append',
    'In '+('topic '*15)+', explain Python lists',
])
def test_misleading_and_unbounded_contexts_abstain(binding,question):
    assert not workflow.is_question(question)
    result=execute(binding,[('recruiter',question),('candidate',ANSWER)])[1]
    assert result.status=='abstained' and not result.suggestions


def test_no_candidate_first_relabel_or_unrelated_answer(binding):
    assert execute(binding,[('candidate',ANSWER),('recruiter',QUESTION)])[1].status=='waiting'
    for answer in ('I travelled by bus.','SQL returns rows.','In Python, explain append'):
        result=execute(binding,[('recruiter',QUESTION),('candidate',answer)])[1]
        assert result.status=='abstained' and not result.suggestions


@pytest.mark.parametrize('requirements',[
    (Requirement(id='sql',description='SQL'),),
    (Requirement(id='python',description='Python'),Requirement(id='list',description='list')),
])
def test_exact_requirement_matching_not_relaxed(binding,requirements):
    b=binding.model_copy(update={'requirements':requirements})
    result=execute(b,[('recruiter',QUESTION),('candidate',ANSWER)])[1]
    assert result.status=='abstained' and result.reason=='ambiguous_association'


def test_generation_and_source_conflicts_still_rejected(binding):
    from app.services.interview_copilot import CopilotLogic
    logic=CopilotLogic(binding);value=update(binding,[('recruiter',QUESTION),('candidate',ANSWER)])
    assert logic.submit(value) is None;assert logic.process(now_ms=6000).status=='suggested'
    assert logic.submit(value).reason=='stale_generation'
    altered=value.events[0].model_copy(update={'text':'Explain Python.'})
    conflict=value.model_copy(update={'generation':2,'events':tuple(e.model_copy(update={'generation':2}) for e in (value.events[0],altered,value.events[1]))})
    assert logic.submit(conflict) is None
    assert logic.process(now_ms=22000).reason=='source_conflict'


def test_exact_pair_through_authorized_bridge_private_delivery_and_withdrawal(runtime):
    async def scenario():
        manager,access,clock,s,b,messages,calls=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        b.offer(s.caption_run_id,100,dict(kind='caption',role='recruiter',sequence=1,start=.1,end=1,text=QUESTION))
        b.offer(s.caption_run_id,100,dict(kind='caption',role='candidate',sequence=2,start=1.1,end=2,text=ANSWER))
        await idle(b)
        assert manager.view(access,recruiter=True)['suggestion']['requirement']=='Python'
        assert 'suggestion' not in manager.view(access)
        assert calls==['fresh','fresh']
        await s.stop()
        assert manager.view(access,recruiter=True)['suggestion'] is None
        assert manager.view(access)['status']=='withdrawn'
    asyncio.run(scenario())


def test_safe_graph_telemetry_uses_plural_suggestions(binding):
    from app.services.copilot_live import graph_result_metadata
    result=execute(binding,[('recruiter',QUESTION),('candidate',ANSWER)])[1]
    assert graph_result_metadata(result)=={'status':'suggested','reason':'valid_suggestion','has_suggestion':True,'suggestion_count':1}
    result=execute(binding,[('candidate',ANSWER)])[1]
    assert graph_result_metadata(result)=={'status':'abstained','reason':'insufficient_context','has_suggestion':False,'suggestion_count':0}


@pytest.mark.parametrize('failure',['unauthorized','withdrawn'])
def test_exact_pair_cannot_publish_without_current_authorization(runtime,failure):
    async def scenario():
        manager,access,clock,s,b,messages,calls=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        if failure=='unauthorized':
            async def denied():raise ValueError('Access denied')
            b.authorize=denied
        else:
            manager.invalidate(access.interview)
        b.offer(s.caption_run_id,100,dict(kind='caption',role='recruiter',sequence=1,start=.1,end=1,text=QUESTION))
        b.offer(s.caption_run_id,100,dict(kind='caption',role='candidate',sequence=2,start=1.1,end=2,text=ANSWER))
        await idle(b)
        assert manager.view(access,recruiter=True)['suggestion'] is None
        assert 'suggestion' not in manager.view(access)
        await s.stop()
    asyncio.run(scenario())
