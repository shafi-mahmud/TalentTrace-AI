"""Disposable Linux maintenance boundary. Never attaches existing volumes/DBs.

Docker/host administrators are trusted: anyone with daemon access can bypass
container isolation. Non-administrative application UID/roles are the boundary.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'talenttrace.n19.lab'


def docker(*args, data=None, check=True):
    r = subprocess.run(['docker', *args], input=data, text=True, capture_output=True)
    if check and r.returncode:
        raise RuntimeError('disposable_docker_operation_failed')
    return r


def save(path, value):
    path.write_text(json.dumps(value, indent=2))
    if os.name != 'nt':
        path.chmod(0o600)


def load(path):
    p = json.loads(path.read_text())
    if not p['name'].startswith('tt-n19-lab-'):
        raise RuntimeError('not_a_disposable_lab')
    for suffix in ('db', 'worker'):
        obj = json.loads(docker('inspect', p['name']+'-'+suffix).stdout)[0]
        if obj['Config']['Labels'].get(LABEL) != p['name']:
            raise RuntimeError('lab_ownership_mismatch')
    return p


def sql(p, statement, *, admin=False):
    role = 'postgres' if admin else 'n19_maintenance'
    password = p['admin_password'] if admin else p['maintenance_password']
    return docker('exec', '-i', '-e', 'PGPASSWORD='+password, p['name']+'-db',
                  'psql', '-h', '127.0.0.1', '-U', role, '-d', 'n19_lab',
                  '-v', 'ON_ERROR_STOP=1', '-At', data=statement).stdout.strip()


def worker(p, code, *, uid=10002, check=True):
    return docker('exec', '-i', '--user', str(uid), p['name']+'-worker',
                  'python', '-B', '-', data=code, check=check)


def storage_boundary(p):
    # No other container, even stopped, may retain a mount to this lab's CV
    # volume. A daemon administrator deliberately mounting it is outside scope.
    ids = docker('ps', '-aq').stdout.split()
    if ids:
        for c in json.loads(docker('inspect', *ids).stdout):
            if c['Name'].lstrip('/') == p['name']+'-worker':
                continue
            if any(m.get('Name') == p['name']+'-cv' for m in c['Mounts']):
                raise RuntimeError('unexpected_storage_mount')
    for volume in ('cv','pg'):
        v=json.loads(docker('volume','inspect',p['name']+'-'+volume).stdout)[0]
        if v['Labels'].get(LABEL)!=p['name']:
            raise RuntimeError('volume_ownership_mismatch')
    # Existing open descriptors held by an application process would survive
    # chmod; refuse while any app UID is running in the only mounted container.
    worker(p, """from pathlib import Path
for f in Path('/proc').glob('[0-9]*/status'):
 try:
  line=next(x for x in f.read_text().splitlines() if x.startswith('Uid:'))
  assert '10001' not in line.split()[1:], 'application_process_present'
 except (FileNotFoundError,ProcessLookupError): pass
""", uid=0)


def init(path, backend_image='talenttrace-docker-demo-backend:latest'):
    if path.exists():
        raise RuntimeError('state_exists_do_not_repeat_provisioning')
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # Inherit only SYSTEM/admin/current owner access for generated secrets.
        user = subprocess.run(['whoami'],capture_output=True,text=True,check=True).stdout.strip()
        subprocess.run(['icacls', str(path.parent), '/inheritance:r', '/grant:r',
                        user+':(OI)(CI)F','SYSTEM:(OI)(CI)F','Administrators:(OI)(CI)F'],
                       capture_output=True,check=True)
    p=dict(name='tt-n19-lab-'+secrets.token_hex(5), admin_password=secrets.token_urlsafe(24),
           maintenance_password=secrets.token_urlsafe(24), application_password=secrets.token_urlsafe(24))
    p['backend_image']=backend_image
    save(path,p)  # Preserve partial-resource ownership for manual recovery.
    image='pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f'
    docker('image','inspect',image)
    docker('image','inspect',backend_image)
    docker('network','create','--internal','--label',LABEL+'='+p['name'],p['name'])
    for volume in ('pg','cv'):
        docker('volume','create','--label',LABEL+'='+p['name'],p['name']+'-'+volume)
    docker('run','--pull=never','-d','--name',p['name']+'-db','--label',LABEL+'='+p['name'],
           '--network',p['name'],'--network-alias','db','-e','POSTGRES_DB=n19_lab',
           '-e','POSTGRES_PASSWORD='+p['admin_password'],'-v',p['name']+'-pg:/var/lib/postgresql/data',image)
    for _ in range(80):
        if docker('exec',p['name']+'-db','pg_isready','-h','127.0.0.1',check=False).returncode==0:
            break
        time.sleep(.25)
    else:
        raise RuntimeError('lab_database_not_ready')
    sql(p, f"""CREATE ROLE n19_application LOGIN PASSWORD '{p['application_password']}';
CREATE ROLE n19_maintenance LOGIN CREATEROLE PASSWORD '{p['maintenance_password']}';
GRANT n19_application TO n19_maintenance WITH ADMIN OPTION;
GRANT pg_read_all_stats TO n19_maintenance;
ALTER DATABASE n19_lab OWNER TO n19_maintenance;
REVOKE CONNECT ON DATABASE n19_lab FROM PUBLIC;
GRANT CONNECT ON DATABASE n19_lab TO n19_application,n19_maintenance;
CREATE EXTENSION IF NOT EXISTS vector;
""",admin=True)
    docker('run','--pull=never','-d','--name',p['name']+'-worker','--label',LABEL+'='+p['name'],
           '--network',p['name'],'--user','10002:10002','--cap-drop','ALL','--security-opt','no-new-privileges:true',
           '-e','PYTHONDONTWRITEBYTECODE=1','-e','DATABASE_URL=postgresql+asyncpg://n19_maintenance:'+p['maintenance_password']+'@db:5432/n19_lab',
           '-e','CV_UPLOAD_ROOT=/cv','-e','N19_LAB_ID='+p['name'],
           '-v',str(ROOT/'backend')+':/app/backend:ro','-v',p['name']+'-cv:/cv',
           '--entrypoint','sleep',backend_image,'infinity')
    # Container capability set is empty. Bootstrap ownership via a short-lived
    # root helper, with only this new volume and no network/source credentials.
    docker('run','--rm','--pull=never','--network','none','--user','0',
           '-v',p['name']+'-cv:/cv','--entrypoint','python',p.get('backend_image','talenttrace-docker-demo-backend:latest'),
           '-c',"import os;os.chown('/cv',10001,10001);os.chmod('/cv',0o700)")
    worker(p,"""from alembic.config import Config
from alembic import command
command.upgrade(Config('alembic.ini'),'head')
""")
    sql(p,'GRANT USAGE ON SCHEMA public TO n19_application; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO n19_application;')
    sql(p,'REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON submission_deletions FROM n19_application;')
    return p


def maintenance(p):
    storage_boundary(p)
    if sql(p,"SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend';") != '0':
        raise RuntimeError('active_database_clients')
    if sql(p,"SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database();") != '0':
        raise RuntimeError('prepared_transactions_present')
    sql(p,'ALTER ROLE n19_application NOLOGIN;')
    # Admission closes before the second check; a racing earlier connection
    # causes refusal and NOLOGIN deliberately remains in place.
    if sql(p,"SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend';") != '0':
        raise RuntimeError('clients_remain_admission_stays_closed')
    docker('run','--rm','--pull=never','--network','none','--user','0',
           '-v',p['name']+'-cv:/cv','--entrypoint','python',p.get('backend_image','talenttrace-docker-demo-backend:latest'),
           '-c',"import os; from pathlib import Path; paths=[Path('/cv'),*Path('/cv').rglob('*')]; assert all(not p.is_symlink() and (p.is_dir() or p.is_file()) and (p.is_dir() or p.stat().st_nlink==1) for p in paths); [(os.chown(p,10002,10002)) for p in paths]; os.chmod('/cv',0o700)")
    storage_boundary(p)
    worker(p,"""import os,json
from pathlib import Path
s=Path('/cv').stat();assert s.st_uid==10002 and s.st_mode&0o777==0o700
Path('/cv/.n19-maintenance.json').write_text(json.dumps({'lab':os.environ['N19_LAB_ID'],'state':'maintenance'}))
""")


def check(p):
    storage_boundary(p)
    worker(p,"""import os,json
from pathlib import Path
assert json.loads(Path('/cv/.n19-maintenance.json').read_text())=={'lab':os.environ['N19_LAB_ID'],'state':'maintenance'}
s=Path('/cv').stat();assert s.st_uid==os.getuid()==10002 and s.st_mode&0o777==0o700
""")
    if sql(p,"SELECT rolcanlogin FROM pg_roles WHERE rolname='n19_application';")!='f':
        raise RuntimeError('application_admission_open')
    if sql(p,"SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend';")!='0':
        raise RuntimeError('unexpected_database_clients')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['init','enter','check'])
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--backend-image',default='talenttrace-docker-demo-backend:latest')
    parser.add_argument('--confirm-new-disposable',action='store_true')
    args=parser.parse_args()
    try:
        if args.action=='init':
            if not args.confirm_new_disposable:
                raise RuntimeError('explicit_new_lab_confirmation_required')
            init(args.state,args.backend_image)
        else:
            p=load(args.state)
            (maintenance if args.action=='enter' else check)(p)
        print(json.dumps(dict(status='verified',action=args.action)))
        return 0
    except Exception:
        print(json.dumps(dict(status='blocked',reason='maintenance_control_failed_no_cleanup_performed')))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
