import asyncio
import pytest
from app.rag.technical_references import CuratedTechnicalRetriever,CORPUS,CORPUS_VERSION
from app.services.interview_qa import pair_transcript
from test_interview_qa import dialogue


@pytest.mark.parametrize('answer',['Python lists can be changed.','Python lists are immutable.',
    'Python lists are not immutable.','A list is an ordered collection.'])
def test_grounding_is_retrieval_not_an_automatic_truth_judgement(answer):
    source=dialogue([('recruiter','Explain Python lists.'),('candidate',answer)])
    refs=asyncio.run(CuratedTechnicalRetriever().retrieve(source,pair_transcript(source)))
    assert refs[0].provenance=='official_documentation_summary'
    assert refs[0].source_title and refs[0].location and refs[0].url.startswith('https://docs.python.org/')
    assert refs[0].version=='3.13' and 'mutable' in refs[0].text and CORPUS_VERSION


@pytest.mark.parametrize('question',['Explain Python 2 lists.','How is the weather?','Describe Java lists.','How do MySQL transactions work?'])
def test_outdated_irrelevant_and_missing_references_abstain(question):
    source=dialogue([('recruiter',question),('candidate','I am unsure.')])
    assert asyncio.run(CuratedTechnicalRetriever().retrieve(source,pair_transcript(source)))==()


def test_paraphrase_and_conflicting_reference_records():
    source=dialogue([('recruiter','Describe a dynamic array.'),('candidate','Its elements can change.')])
    assert asyncio.run(CuratedTechnicalRetriever().retrieve(source,pair_transcript(source)))[0].id=='python313-lists-v1'
    conflicting=(*CORPUS,{**CORPUS[0],'text':'Conflicting text.'})
    assert asyncio.run(CuratedTechnicalRetriever(corpus=conflicting).retrieve(source,pair_transcript(source)))==()


def test_existing_embedding_boundary_is_reused_without_external_calls():
    class Embedding:
        def embed_documents(self,texts):return tuple((1.,0.) for _ in texts)
        def embed_query(self,text):return (1.,0.)
    source=dialogue([('recruiter','Explain Python sequences.'),('candidate','They preserve order.')])
    refs=asyncio.run(CuratedTechnicalRetriever(Embedding()).retrieve(source,pair_transcript(source)))
    assert refs and refs[0].retrieval_basis=='curated_alias_and_local_bge'
