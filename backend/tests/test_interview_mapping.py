import asyncio
from app.services.interview_qa import pair_transcript
from app.services.interview_mapping import map_requirements, SyntheticTechnicalRetriever
from test_interview_qa import dialogue


def test_literal_topic_not_claimed_as_skill_and_missing_is_gap():
    data=dialogue([('recruiter','What is Python?'),('candidate','A language.')])
    mapped=map_requirements(data,pair_transcript(data))[0]
    assert mapped.coverage=='partial' and mapped.turn_ids
    data=dialogue([('recruiter','What is Java?'),('candidate','A language.')])
    mapped=map_requirements(data,pair_transcript(data))[0]
    assert mapped.coverage=='not_evidenced' and not mapped.turn_ids


def test_negation_and_uncertainty_preserved():
    data=dialogue([('recruiter','Describe Python experience.'),('candidate','I have never used Python in production.')])
    mapped=map_requirements(data,pair_transcript(data))[0]
    assert mapped.coverage=='uncertain'
    assert 'never' in data.turns[1].text


def test_reference_boundary_is_explicit_synthetic_not_company_policy():
    data=dialogue([('recruiter','What is Python?'),('candidate','Lists are immutable.')])
    refs=asyncio.run(SyntheticTechnicalRetriever().retrieve(data,pair_transcript(data)))
    assert len(refs)==1 and refs[0].provenance=='synthetic_demo'
    assert 'mutable' in refs[0].text
