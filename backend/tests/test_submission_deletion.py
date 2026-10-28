"""Offline deletion policy/file tests; no private data or provider calls."""
import asyncio
from dataclasses import replace
from uuid import uuid4
import pytest
from app.services.candidate_inventory import Target
from app.services.submission_deletion import (DeletionError, source_digest, exact_file,
    fingerprint, validate_inventory, make_plan, import_suppressed)


def observed():
    return {'categories':{
        'imported_submissions':{'status':'confirmed','count':1},
        'cv_files':{'status':'confirmed','count':1},
        'screening_versions':{'status':'confirmed','count':2},
        'global_candidate_identity':{'status':'unsupported','count':None},
        'interviews_and_screening_snapshots':{'status':'missing','count':0}}}


def test_exact_target_digest_and_scope():
    t=Target(uuid4(),uuid4(),uuid4(),uuid4());o=observed()
    p=make_plan(t,o,'a'*64)
    assert p==make_plan(t,o,'a'*64)
    assert p!=make_plan(replace(t,upload_id=uuid4()),o,'a'*64)
    assert p!=make_plan(t,o,'b'*64)
    assert p['plan']['scope']=='one_imported_submission_not_person'
    assert source_digest('ab','c')!=source_digest('a','bc')


@pytest.mark.parametrize('name,status,count',[
    ('imported_submissions','missing',0),('cv_files','missing',0),
    ('cv_files','ambiguous',2),('shared_bulk_operations','ambiguous',1),
    ('unmapped_referencing_tables','unsupported',1),
    ('interviews_and_screening_snapshots','confirmed',1),
    ('booked_email_attempts','confirmed',1),
    ('scheduling_invitations','confirmed',1),('legacy_cross_job_references','ambiguous',1)])
def test_incomplete_or_related_data_blocks(name,status,count):
    o=observed();o['categories'][name]={'status':status,'count':count}
    with pytest.raises(DeletionError):validate_inventory(o)


def test_owned_exact_file_and_unrelated_preserved(tmp_path):
    t=Target(uuid4(),uuid4(),uuid4(),uuid4());ref='TT-JOB-0123456789ABCDEF'
    p=exact_file(tmp_path,t,ref,'pdf');p.parent.mkdir(parents=True)
    p.write_bytes(b'synthetic');other=p.with_name(str(uuid4())+'.pdf');other.write_bytes(b'unrelated')
    assert fingerprint(p)==__import__('hashlib').sha256(b'synthetic').hexdigest()
    with pytest.raises(DeletionError):exact_file(tmp_path,t,ref,'txt')
    assert other.read_bytes()==b'unrelated'


def test_symlink_refused_when_platform_can_create_it(tmp_path):
    t=Target(uuid4(),uuid4(),uuid4(),uuid4());ref='TT-JOB-0123456789ABCDEF'
    p=exact_file(tmp_path,t,ref,'pdf');p.parent.mkdir(parents=True)
    other=p.with_name(str(uuid4())+'.pdf');other.write_bytes(b'unrelated')
    try:
        p.symlink_to(other)
    except OSError as error:
        if getattr(error,'winerror',None)==1314:
            pytest.skip('Windows symlink privilege unavailable; rerun in Linux lab')
        raise
    with pytest.raises(DeletionError):exact_file(tmp_path,t,ref,'pdf')
    assert other.read_bytes()==b'unrelated'


def test_hardlink_refused(tmp_path):
    t=Target(uuid4(),uuid4(),uuid4(),uuid4());ref='TT-JOB-0123456789ABCDEF'
    p=exact_file(tmp_path,t,ref,'pdf');p.parent.mkdir(parents=True)
    other=p.with_name(str(uuid4())+'.pdf');other.write_bytes(b'unrelated')
    __import__('os').link(other,p)
    with pytest.raises(DeletionError):exact_file(tmp_path,t,ref,'pdf')
    assert other.read_bytes()==b'unrelated'


def test_import_tombstone_lookup():
    class DB:
        def __init__(self,answers):self.answers=iter(answers)
        async def scalar(self,*args):return next(self.answers)
    assert asyncio.run(import_suppressed(DB([None]),'source','id')) is False
    assert asyncio.run(import_suppressed(DB(['submission_deletions',1]),'source','id')) is True
    assert asyncio.run(import_suppressed(DB(['submission_deletions',None]),'source','id')) is False


def test_cli_needs_explicit_confirmation_and_sanitizes_identity():
    import subprocess,sys
    from pathlib import Path
    cli=Path(__file__).resolve().parents[2]/'docker/n19_delete.py'
    ids=[item for key in ['recruiter','job','batch','upload'] for item in ['--'+key+'-id',str(uuid4())]]
    r=subprocess.run([sys.executable,str(cli),'execute','--state','missing.json',*ids],capture_output=True,text=True)
    assert r.returncode==2 and 'confirmation' in r.stderr
    r=subprocess.run([sys.executable,str(cli),'preview','--state','missing.json','--recruiter-id','sensitive@example.test'],capture_output=True,text=True)
    assert r.returncode==2 and 'sensitive@example.test' not in r.stderr
