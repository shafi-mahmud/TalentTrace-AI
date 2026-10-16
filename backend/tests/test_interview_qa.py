from uuid import uuid4
import pytest
from app.services.evaluation_input import build_input, EvaluationInputError
from app.services.interview_qa import pair_transcript, validate_pairs
from test_evaluation_input import source


def dialogue(lines):
    parent,snapshot,captures,rows=source();template=rows[0]
    from types import SimpleNamespace as N
    rows=[N(id=uuid4(),session_id=template.session_id,sequence=i+1,role=role,text=text,
        start_ms=i*100,end_ms=(i+1)*100) for i,(role,text) in enumerate(lines)]
    captures[0].capture_summary['expected_turns']=len(rows)
    captures[0].capture_summary['acknowledged_turns']=len(rows)
    return build_input(parent,snapshot,captures,rows)


def test_normal_multiturn_followup_and_unanswered():
    data=dialogue([('recruiter','What is Python?'),('candidate','A programming language.'),
        ('candidate','I use lists.'),('recruiter','How do lists work?'),('candidate','They preserve order.'),
        ('recruiter','Why choose tuples?')])
    pairs=pair_transcript(data)
    assert len(pairs)==3 and len(pairs[0].answer_turns)==2
    assert pairs[-1].status=='unanswered' and pairs[-1].answer==''
    assert pairs[1].status=='answered'


def test_clarification_interruption_uncertain_not_incorrect_answer():
    data=dialogue([('recruiter','Explain Python lists.'),('candidate','Do you mean mutable lists?'),
        ('recruiter','Yes, continue.'),('candidate','They are mutable.')])
    pair=pair_transcript(data)[0]
    assert pair.status=='uncertain' and pair.answer=='They are mutable.'
    assert len(pair.warnings)==2


@pytest.mark.parametrize('change',['reference','speaker','quotation'])
def test_hallucinated_or_wrong_role_references_rejected(change):
    data=dialogue([('recruiter','What is Python?'),('candidate','A language.')])
    pairs=pair_transcript(data);p=pairs[0]
    patch={'question_turns':(uuid4(),)} if change=='reference' else {'answer_turns':p.question_turns} if change=='speaker' else {'answer':'Invented answer'}
    with pytest.raises(EvaluationInputError):validate_pairs(data,(p.model_copy(update=patch),))


def test_nonquestion_dialogue_is_not_invented_question():
    data=dialogue([('recruiter','Welcome to this interview.'),('candidate','Thank you.')])
    assert pair_transcript(data)==()
