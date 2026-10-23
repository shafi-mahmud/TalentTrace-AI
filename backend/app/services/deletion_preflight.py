"""Read-only maintenance observations and deterministic, non-executable manifest."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from sqlalchemy import text

from app.services.candidate_inventory import Target, inventory, file_inventory


def runtime_observations():
    """Best-effort hints, never proof of which configuration a process loaded.

    Do not return command lines, PIDs, environment, URLs or scheduler arguments.
    psutil is optional: no new runtime dependency is required by this increment.
    """
    counts = dict(backend_or_cli=0, stt=0, livekit=0, frontend=0)
    result = dict(visibility='unknown', known_processes=counts,
                  inaccessible_processes=0, other_python_processes=0,
                  target_access='unknown', scheduled_launchers='unknown',
                  process_managers='unknown', containers='unknown')
    try:
        import psutil
        for process in psutil.process_iter(['name', 'cmdline']):
            try:
                if process.pid == os.getpid():
                    continue
                name = (process.info['name'] or '').lower()
                command = ' '.join(process.info['cmdline'] or []).lower()
                relevant = 'talenttrace' in command
                if 'livekit' in name:
                    counts['livekit'] += 1
                elif 'python' in name:
                    if 'local_whisper_worker' in command:
                        counts['stt'] += 1
                    elif relevant:
                        counts['backend_or_cli'] += 1
                    else:
                        result['other_python_processes'] += 1
                elif 'node' in name and relevant:
                    counts['frontend'] += 1
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                result['inaccessible_processes'] += 1
        result['visibility'] = 'partial'
    except (ImportError, OSError):
        pass
    try:
        response = subprocess.run(['docker', 'ps', '--format', '{{.Image}}'],
                                  capture_output=True, text=True, timeout=5)
        if response.returncode == 0:
            images = response.stdout.splitlines()
            result['containers'] = 'partial'
            result['possible_project_containers'] = sum('talenttrace' in image.lower() for image in images)
    except (OSError, subprocess.TimeoutExpired):
        pass
    # Deliberately do not equate no matching command line with no writers.
    return result


async def database_observations(session):
    if session.in_transaction():
        raise ValueError('fresh_session_required')
    async with session.begin():
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        identity = (await session.execute(text("""
            SELECT current_database() AS database, current_user AS role,
                   r.rolsuper AS superuser, r.rolcreaterole AS create_role,
                   pg_has_role(current_user,'pg_read_all_stats','MEMBER') AS read_all_stats
            FROM pg_roles r WHERE r.rolname=current_user
        """))).mappings().one()
        full = bool(identity['superuser'] or identity['read_all_stats'])
        activity = (await session.execute(text("""
            SELECT count(*) AS other_connections,
                count(*) FILTER (WHERE state='active') AS active_connections,
                count(*) FILTER (WHERE xact_start IS NOT NULL) AS open_transactions,
                count(*) FILTER (WHERE state IS NULL) AS hidden_states
            FROM pg_stat_activity WHERE datname=current_database()
                AND pid<>pg_backend_pid() AND backend_type='client backend'
        """))).mappings().one()
        prepared = await session.scalar(text(
            'SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database()'))
        return dict(status='observed', **dict(identity), **dict(activity),
                    prepared_transactions=prepared, full_activity_visibility=full,
                    administration_capability='superuser' if identity['superuser'] else 'not_established')


def storage_observations(root: Path):
    try:
        root = root.absolute()
        if root == Path(root.anchor) or any(p.is_symlink() or p.is_junction() for p in [root, *root.parents]):
            return dict(status='blocked', reason='unsafe_storage_root', exclusivity='not_established')
        if not root.is_dir():
            return dict(status='blocked', reason='storage_unavailable', exclusivity='not_established')
        readable = os.access(root, os.R_OK | os.X_OK)
        return dict(status='observed' if readable else 'blocked',
                    reason='metadata_only' if readable else 'storage_access_unavailable',
                    exclusivity='not_established')
    except OSError:
        return dict(status='unknown', reason='storage_inspection_unavailable', exclusivity='not_established')


def manifest(target: Target, observation, files=None):
    """Stable for the same target/inventory; excludes volatile runtime evidence.

    Explicit association selectors plus counts, not executable DELETE statements.
    No record payloads, contact values, capability hashes or absolute paths.
    """
    categories = observation['categories']
    plan = dict(version=1, scope='exact_submission_only',
                target={k: str(v) for k, v in target.parameters().items()},
                confirmed_database_associations={k: v for k, v in categories.items()
                    if v['status'] == 'confirmed' and k != 'cv_files'},
                files=dict(root='configured_CV_UPLOAD_ROOT', relative_paths=sorted(files or []),
                           observation=categories['cv_files']),
                shared_artifacts={k: v for k, v in categories.items() if k == 'shared_bulk_operations'},
                unresolved={k: v for k, v in categories.items() if v['status'] in {'ambiguous', 'unsupported'}},
                missing={k: v for k, v in categories.items() if v['status'] == 'missing'},
                blockers=sorted(set(observation['blockers'])),
                limitations=sorted(observation['limitations']),
                candidate_wide_deletion_resolved=False, deletion_authorized=False)
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(status='ready_for_review', digest=digest, plan=plan)


def assess(database, storage, runtime, plan_available):
    blockers = {'exclusive_database_access_not_enforced', 'storage_exclusivity_not_established',
                'durable_restart_block_unavailable', 'independent_writers_not_excluded',
                'livekit_cached_token_revocation_unresolved', 'candidate_wide_scope_unresolved'}
    if database.get('status') != 'observed':
        blockers.add('database_observation_unavailable')
    else:
        if database['other_connections']:
            blockers.add('other_database_connections_present')
        if database['open_transactions'] or database['prepared_transactions']:
            blockers.add('transactions_present')
        if not database['full_activity_visibility'] or database['hidden_states']:
            blockers.add('database_activity_visibility_incomplete')
        if database['administration_capability'] != 'superuser':
            blockers.add('maintenance_privileges_not_established')
    if storage['status'] != 'observed':
        blockers.add(storage['reason'])
    if any(runtime.get('known_processes', {}).values()):
        blockers.add('known_services_observed')
    if not plan_available:
        blockers.add('inventory_unavailable')
    return dict(state='unknown' if database.get('status') != 'observed' else 'blocked',
                deletion_ready=False, mutation_performed=False,
                independent_writers='not_excluded', durable_restart_block='unavailable',
                blockers=sorted(blockers))


async def preflight(factory, target: Target, root: Path, *, runtime=None):
    target.parameters()
    try:
        async with factory() as session:
            db = await database_observations(session)
    except Exception:
        db = dict(status='unknown', reason='database_observation_unavailable')
    try:
        async with factory() as session:
            observed = await inventory(session, target, root)
        # A second bounded metadata observation, not a transactional filesystem
        # snapshot. Any difference blocks file enumeration rather than guessing.
        async with factory() as session:
            async with session.begin():
                await session.execute(text('SET TRANSACTION READ ONLY'))
                reference = await session.scalar(text('SELECT job_reference FROM job_profiles '
                    'WHERE id=:job_id AND recruiter_id=:recruiter_id'), target.parameters())
        files = []
        if reference is None:
            raise ValueError('owned_scope_changed')
        check = file_inventory(root, target, reference)
        if check != observed['categories']['cv_files']:
            observed['blockers'].append('filesystem_changed_during_preview')
            observed['categories']['cv_files'] = dict(status='ambiguous', count=None, reason='filesystem_changed_during_preview')
        elif check['status']=='confirmed':
            relative = Path(str(target.recruiter_id)) / reference / str(target.batch_id)
            files = [(relative / (str(target.upload_id)+suffix)).as_posix()
                     for suffix in ('.pdf','.docx') if (root / relative / (str(target.upload_id)+suffix)).is_file()]
        preview = manifest(target, observed, files)
    except Exception:
        preview = dict(status='unavailable', reason='inventory_or_owned_scope_unavailable')
    storage = storage_observations(root)
    runtime = runtime if runtime is not None else runtime_observations()
    return dict(preflight=assess(db, storage, runtime, preview['status']=='ready_for_review'),
                database=db, storage=storage, runtime=runtime, manifest=preview,
                configuration=dict(database_source='configured_DATABASE_URL_credentials_withheld',
                                   storage_source='configured_CV_UPLOAD_ROOT_path_withheld'),
                limitations=['observations_not_atomic_across_database_storage_and_processes',
                             'process_hints_do_not_prove_database_or_storage_access',
                             'no_maintenance_mode_entered', 'no_deletion_performed'])
