"""Curated attributable summaries. No runtime web scraping or cloud embedding."""
import asyncio
import hashlib
import json
import re
from pathlib import Path
from app.services.interview_mapping import TechnicalReference
from app.rag.embeddings import BGEEmbeddingService

# Short paraphrases reviewed against official documentation on 16 October 2026.
CORPUS=(
 dict(id='python313-lists-v1',topic='python lists',text='Python lists are mutable ordered sequences. Existing elements can be replaced, and append adds an element at the end.',source_title='Python 3.13 Tutorial: Data Structures',document_id='python-3.13-tutorial',location='5.1 More on Lists',url='https://docs.python.org/3.13/tutorial/datastructures.html#more-on-lists',version='3.13',aliases=('python list','lists','mutable sequence','dynamic array','change list elements')),
 dict(id='python313-tuples-v1',topic='python tuples',text='A Python tuple cannot have its items reassigned. A tuple may contain a mutable object whose own contents can change.',source_title='Python 3.13 Tutorial: Data Structures',document_id='python-3.13-tutorial',location='5.3 Tuples and Sequences',url='https://docs.python.org/3.13/tutorial/datastructures.html#tuples-and-sequences',version='3.13',aliases=('python tuple','tuples','immutable collection')),
 dict(id='python313-coroutines-v1',topic='python asyncio',text='Calling an async coroutine function creates a coroutine object; execution requires awaiting it or scheduling it as a task.',source_title='Python 3.13: Coroutines and Tasks',document_id='python-3.13-asyncio',location='Coroutines',url='https://docs.python.org/3.13/library/asyncio-task.html#coroutines',version='3.13',aliases=('asyncio','coroutine','async def','await','asynchronous function','event loop')),
 dict(id='postgres18-transactions-v1',topic='postgresql transactions',text='A transaction groups database operations into an all-or-nothing unit. COMMIT makes its changes effective; ROLLBACK cancels them.',source_title='PostgreSQL 18 Tutorial: Transactions',document_id='postgresql-18-tutorial',location='3.4 Transactions',url='https://www.postgresql.org/docs/18/tutorial-transactions.html',version='18',aliases=('transaction','transactions','commit','rollback','all or nothing','atomic database')),
 dict(id='rfc9110-get-v1',topic='http get',text='HTTP GET requests transfer of a current selected representation of the target resource. GET is defined as a safe method; safety describes intended semantics, not every possible server side effect.',source_title='RFC 9110: HTTP Semantics',document_id='rfc9110',location='9.3.1 GET; 9.2.1 Safe Methods',url='https://httpwg.org/specs/rfc9110.html#GET',version='2022',aliases=('http get','get request','safe method','retrieve resource')),
)
CORPUS_VERSION='official-curated-v1-'+hashlib.sha256(json.dumps(CORPUS,sort_keys=True).encode()).hexdigest()[:12]
def words(text):return set(re.findall(r'[a-z0-9]+',text.lower()))


class CuratedTechnicalRetriever:
    def __init__(self,embedding=None,corpus=CORPUS):
        self.embedding,self.corpus=embedding,corpus
        self._vectors=None;self._lock=asyncio.Lock()

    async def retrieve(self,source,pairs):
        query=' '.join(p.question+' '+p.answer for p in pairs).lower()
        if re.search(r'\b(python\s*2|postgres(?:ql)?\s*(?:8|9)\b)',query):return ()
        lexical=[r for r in self.corpus if any(words(alias).issubset(words(query)) for alias in r['aliases'])]
        if 'python' not in words(query) and words(query)&{'java','javascript','typescript','rust'}:
            lexical=[r for r in lexical if not r['topic'].startswith('python')]
        if 'mysql' in words(query) and 'postgresql' not in words(query):
            lexical=[r for r in lexical if not r['topic'].startswith('postgresql')]
        candidates=list(lexical);basis='curated_alias_match'
        if self.embedding:
            async with self._lock:
                if self._vectors is None:self._vectors=await asyncio.to_thread(self.embedding.embed_documents,[r['text'] for r in self.corpus])
            vector=await asyncio.to_thread(self.embedding.embed_query,query[:2000])
            ranked=sorted(zip(self.corpus,self._vectors),key=lambda r:sum(a*b for a,b in zip(vector,r[1])),reverse=True)
            candidates+= [r for r,v in ranked[:2] if sum(a*b for a,b in zip(vector,v))>=.65 and r not in lexical and r['topic'].split()[0] in words(query)]
            basis='curated_alias_and_local_bge'
        identities={}
        for r in candidates:
            if r['id'] in identities and identities[r['id']]['text']!=r['text']:return ()
            identities[r['id']]=r
        return tuple(TechnicalReference(**{k:v for k,v in r.items() if k!='aliases'},provenance='official_documentation_summary',retrieval_basis=basis) for r in list(identities.values())[:5])


def configured_retriever(path=None):
    if not path:return CuratedTechnicalRetriever()
    path=Path(path)
    if not path.is_dir() or not (path/'config.json').is_file():raise ValueError('Local technical embedding model unavailable')
    def backend():
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(str(path),device='cpu',local_files_only=True,trust_remote_code=False,token=False)
    return CuratedTechnicalRetriever(BGEEmbeddingService(backend_factory=backend))
