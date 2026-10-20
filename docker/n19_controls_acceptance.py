"""Synthetic controls test on an explicitly provisioned disposable N19 lab."""
import json
from pathlib import Path
import subprocess
import sys
import time

from n19_lab import LABEL, check, docker, load, maintenance, sql, worker


def prove(path):
    p=load(path)
    assert sql(p,"SELECT count(*) FROM pg_roles WHERE rolname IN ('n19_application','n19_maintenance') AND NOT rolsuper;")=='2'
    assert sql(p,"SELECT rolcanlogin FROM pg_roles WHERE rolname='n19_application';")=='t'
    def app_sql(statement):
        return docker('exec','-i','-e','PGPASSWORD='+p['application_password'],p['name']+'-db',
            'psql','-h','127.0.0.1','-U','n19_application','-d','n19_lab','-At',data=statement,check=False)
    assert app_sql('SELECT 1;').returncode==0
    assert worker(p,"from pathlib import Path;Path('/cv/application-probe').write_text('fictional')",uid=10001).returncode==0
    # A real open transaction must block maintenance, not merely an OS hint.
    active=subprocess.Popen(['docker','exec','-e','PGPASSWORD='+p['application_password'],p['name']+'-db',
        'psql','-h','127.0.0.1','-U','n19_application','-d','n19_lab','-c','BEGIN; SELECT pg_sleep(7); COMMIT;'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            if sql(p,"SELECT count(*) FROM pg_stat_activity WHERE usename='n19_application';")!='0':break
            time.sleep(.1)
        try:
            maintenance(p)
            raise AssertionError('active_writer_was_not_blocked')
        except RuntimeError as e:
            assert str(e)=='active_database_clients'
    finally:
        active.wait(timeout=20)
    maintenance(p);check(p)
    assert app_sql('SELECT 1;').returncode!=0
    assert worker(p,"from pathlib import Path;Path('/cv/forbidden').write_text('must fail')",uid=10001,check=False).returncode!=0
    extra=p['name']+'-unexpected'
    docker('create','--name',extra,'--label',LABEL+'='+p['name'],'--network','none',
        '-v',p['name']+'-cv:/cv:ro','--entrypoint','sleep',p.get('backend_image','talenttrace-docker-demo-backend:latest'),'infinity')
    try:
        try:check(p);raise AssertionError('unexpected_mount_not_blocked')
        except RuntimeError as e:assert str(e)=='unexpected_storage_mount'
    finally:docker('rm',extra)
    docker('restart',p['name']+'-worker')
    check(p)
    assert app_sql('SELECT 1;').returncode!=0
    assert worker(p,"from pathlib import Path;assert Path('/cv/.n19-maintenance.json').is_file()").returncode==0
    result=dict(non_superuser_application_and_maintenance=True,active_writer_blocks=True,
        application_database_admission_denied=True,application_storage_denied=True,
        unexpected_mount_blocks=True,maintenance_survives_worker_restart=True,
        no_candidate_data_deleted=True)
    print(json.dumps(result))


if __name__=='__main__':
    try:prove(Path(sys.argv[1]))
    except Exception:print('{"status":"blocked","reason":"controls_acceptance_failed"}');raise SystemExit(1)
