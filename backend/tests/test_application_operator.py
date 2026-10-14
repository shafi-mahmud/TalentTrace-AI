import pytest
from app import application_import as cli

def test_confirmation_required_never_loads_configuration(monkeypatch,capsys):
 monkeypatch.setattr('sys.argv',['application_import','--submission','synthetic'])
 monkeypatch.setattr(cli,'load_configuration',lambda:pytest.fail('Must not load/import without confirmation'))
 assert cli.main()==1
 assert 'confirmation_required' in capsys.readouterr().out

def test_configuration_failure_is_sanitized(monkeypatch,capsys):
 monkeypatch.setattr('sys.argv',['application_import','--submission','synthetic','--confirm-synthetic-import'])
 def fail():raise ValueError('private credential value')
 monkeypatch.setattr(cli,'load_configuration',fail)
 assert cli.main()==1
 output=capsys.readouterr().out;assert 'application_import_failed' in output and 'private credential' not in output

@pytest.mark.parametrize('case',['valid','source_database','overlap','query'])
def test_fixed_private_configuration_identity_checks(tmp_path,monkeypatch,case):
 import json
 from uuid import uuid4
 from types import SimpleNamespace
 from app.services.application_bridge import ApplicationBridgeError
 folder=tmp_path/'data'/'application_bridge';folder.mkdir(parents=True)
 value=dict(source_database_url='postgresql+asyncpg://reader:synthetic@127.0.0.1:54379/talenttrace_external_intake',target_database_url='postgresql+asyncpg://writer:synthetic@127.0.0.1:54378/talenttrace_f4_local',source_storage_root=str(tmp_path/'source'),target_storage_root=str(tmp_path/'target'),binding=dict(intake_recruiter_id=str(uuid4()),intake_job_id=str(uuid4()),target=dict(source_id='synthetic_google',source_job_reference='TT-JOB-AAAAAAAAAAAAAAAA',recruiter_id=str(uuid4()),target_job_id=str(uuid4()),target_job_reference='TT-JOB-BBBBBBBBBBBBBBBB')))
 if case=='source_database':value['source_database_url']=value['target_database_url']
 if case=='query':value['source_database_url']+='?host=other'
 if case=='overlap':value['target_storage_root']=value['source_storage_root']
 (folder/'configuration.json').write_text(json.dumps(value))
 monkeypatch.setattr(cli,'REPOSITORY_ROOT',tmp_path);monkeypatch.setattr(cli,'private_file',lambda p:True)
 monkeypatch.setattr(cli.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=b''))
 if case=='valid':assert cli.load_configuration().binding.target.source_id=='synthetic_google'
 else:
  with pytest.raises(ApplicationBridgeError):cli.load_configuration()
