"""Explicit synthetic integration test for this disposable Compose project only.

Run after building, starting db and explicitly migrating it. Never logs credentials.
Does not migrate, send mail, publish, invoke inference or access existing office DBs.
"""
import argparse
import hashlib
import http.client
import http.cookiejar
import json
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'talenttrace-docker-demo'


def run(args, *, stdin=None):
    # Windows text pipes translate LF to CRLF. Linux getpass preserves that CR,
    # so operator test input must be byte-exact (never change password semantics).
    result = subprocess.run(args, input=stdin.encode('utf-8') if stdin is not None else None,
                            capture_output=True, cwd=ROOT)
    if result.returncode:
        # Subprocess output might contain a DSN, env value or provisioning input.
        raise RuntimeError('Docker verification command failed; inspect locally without sharing private output.')
    return result.stdout.decode('utf-8')


def main(env_file, allow_synthetic_records):
    compose = ['docker', 'compose', '-p', PROJECT, '--env-file', str(env_file)]
    config = json.loads(run(compose + ['config', '--format', 'json']))
    assert config['name'] == PROJECT
    assert set(config['services']) == {'db', 'backend', 'frontend'}
    assert config['networks']['private']['internal'] is True
    assert set(config['services']['db']['networks']) == {'private'}
    assert set(config['services']['backend']['networks']) == {'private'}
    assert set(config['services']['frontend']['networks']) == {'edge', 'private'}
    assert not config['services']['db'].get('ports')
    assert not config['services']['backend'].get('ports')
    assert not any(v.get('external') for v in config['volumes'].values())
    assert config['services']['frontend']['ports'][0]['host_ip'] == '127.0.0.1'
    for service in config['services'].values():
        assert all(v['type'] == 'volume' for v in service.get('volumes', []))
    port = int(config['services']['frontend']['ports'][0]['published'])
    base = f'http://127.0.0.1:{port}'
    checks = []

    def passed(label):
        checks.append(label)
        print('PASS: ' + label, flush=True)

    def backend_python(source):
        return run(compose + ['exec', '-T', 'backend', 'python', '-'], stdin=source).strip()

    def db_snapshot():
        return json.loads(backend_python('''
import asyncio,json
from sqlalchemy import text
from app.db.session import create_database_engine
async def main():
 e=create_database_engine()
 try:
  async with e.connect() as c:
   identity=(await c.execute(text("SELECT current_database(),current_user"))).one()
   revision=(await c.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
   count=(await c.execute(text("SELECT count(*) FROM recruiters"))).scalar_one()
   print(json.dumps({'database':identity[0],'role':identity[1],'revision':revision,'recruiters':count}))
 finally: await e.dispose()
asyncio.run(main())
'''))

    passed('three services, private backend/database, project-scoped volumes and loopback frontend')
    before = db_snapshot()
    assert before['database'] == 'talenttrace_docker_demo'
    assert before['role'] == 'talenttrace_demo'
    assert before['revision'] == '0015_reviewer_confirmation'
    passed('isolated database identity and explicit migration through 0015')

    backend_python('''
import os
from pathlib import Path
from app.core.config import settings
assert not Path('/app/.env').exists()
assert not Path('/app/data/study').exists()
assert not any([settings.interview_email_enabled,settings.livekit_synthetic_demo_enabled,
 settings.interview_evaluation_enabled,settings.interview_evaluation_durable_enabled,
 settings.transcript_storage_enabled,settings.reviewer_confirmation_enabled])
assert not settings.groq_api_key and not settings.livekit_api_key and not settings.interview_smtp_password
assert 'DISCORD_WEBHOOK_URL' not in os.environ
assert os.getuid()==10001
print('safe')
''')
    passed('non-root backend, no copied office config/data, optional integrations disabled')
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, body=None, *, origin=None):
        headers = {'X-TalentTrace-Request': '1', 'Origin': origin or base}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with opener.open(req, timeout=15) as response:
                return response.status, response.read(), {k.lower(): v for k, v in response.headers.items()}
        except HTTPError as error:
            return error.code, error.read(), {k.lower(): v for k, v in error.headers.items()}

    assert request('/')[0] == 200
    code, body, _ = request('/api/v1/health')
    assert code == 200 and json.loads(body)['service'] == 'talenttrace-api'
    assert request('/api/v1/auth/me')[0] == 401
    assert request('/interview-schedule')[0] == 200
    for path in ['/docs', '/redoc', '/openapi.json', '/.env', '/data/private', '/debug', '/assets/private.map']:
        assert request(path)[0] == 404
    passed('frontend, SPA route, health/API proxy, unauthenticated denial and private-path exclusions')

    # Real HTTP Upgrade through nginx to the disabled, authorized caption route.
    # A denied handshake is expected: never enable captions just to test routing.
    nginx = run(compose + ['exec', '-T', 'frontend', 'nginx', '-T'])
    assert 'proxy_http_version 1.1' in nginx
    assert 'proxy_set_header Upgrade $http_upgrade' in nginx
    assert 'proxy_set_header Connection $connection_upgrade' in nginx
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    connection.request('GET', '/api/v1/interview-access/captions', headers={
        'Origin': base, 'Connection': 'Upgrade', 'Upgrade': 'websocket',
        'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'MDEyMzQ1Njc4OWFiY2RlZg=='})
    response = connection.getresponse()
    assert response.status == 403
    connection.close()
    passed('nginx Upgrade configuration and actual disabled-caption WebSocket rejection')

    if not allow_synthetic_records:
        print('Read-only checks finished. Pass --allow-synthetic-records for explicit provisioning/recreation tests.')
        return

    email = 'docker-smoke-' + uuid.uuid4().hex + '@example.test'
    password = secrets.token_urlsafe(32)
    run(compose + ['exec', '-T', 'backend', 'python', '-m', 'app.db.provision_recruiter'],
        stdin=f'{email}\n{password}\n{password}\n')
    assert db_snapshot()['recruiters'] == before['recruiters'] + 1
    credentials = {'email': email, 'password': password}
    assert request('/api/v1/auth/login', credentials, origin='https://untrusted.invalid')[0] == 403
    code, body, headers = request('/api/v1/auth/login', credentials)
    assert code == 200
    account_id = json.loads(body)['id']
    assert 'HttpOnly' in headers.get('set-cookie', '')
    assert 'SameSite=strict' in headers.get('set-cookie', '')
    assert request('/api/v1/auth/me')[0] == 200
    assert json.loads(request('/api/v1/jobs')[1]) == []
    assert 'no-store' in request('/api/v1/jobs')[2].get('cache-control', '')
    passed('explicit synthetic provisioning, real login/session, origin protection and owned empty workspace')

    marker = secrets.token_hex(16)
    marker_hash = hashlib.sha256(marker.encode()).hexdigest()
    backend_python("from pathlib import Path;Path('/app/data/docker-smoke-marker').write_text(" + repr(marker) + ")")
    # Recreate this project only. Named volumes are deliberately retained.
    old_ids = run(compose + ['ps', '-q']).split()
    run(compose + ['down'])
    run(compose + ['up', '-d', '--wait', '--wait-timeout', '180'])
    new_ids = run(compose + ['ps', '-q']).split()
    assert old_ids and new_ids and set(old_ids).isdisjoint(new_ids)
    after = db_snapshot()
    assert after == {**before, 'recruiters': before['recruiters'] + 1}
    assert json.loads(request('/api/v1/auth/me')[1])['id'] == account_id
    actual_hash = backend_python("import hashlib;from pathlib import Path;print(hashlib.sha256(Path('/app/data/docker-smoke-marker').read_bytes()).hexdigest())")
    assert actual_hash == marker_hash
    assert request('/api/v1/auth/logout', {})[0] == 200
    assert request('/api/v1/auth/me')[0] == 401
    passed('all containers recreated; PostgreSQL, session and private application volume persisted; logout verified')
    print(f'Completed {len(checks)} grouped checks. No external inference, publication, mail or media was requested.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--allow-synthetic-records', action='store_true',
                        help='Explicitly provision one fictional recruiter and recreate this project only.')
    args = parser.parse_args()
    try:
        main(args.env_file.resolve(), args.allow_synthetic_records)
    except Exception:
        print('FAIL: verification stopped; no automatic retry or private output emitted.', file=sys.stderr)
        raise SystemExit(1) from None
