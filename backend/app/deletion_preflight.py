"""Read-only administrative maintenance preview; never grants deletion readiness."""
import argparse
import asyncio
import json
from uuid import UUID

from app.core.config import settings
from app.db.session import create_database_engine, create_database_session_factory
from app.services.candidate_inventory import Target
from app.services.deletion_preflight import preflight


async def run(args):
    engine = create_database_engine(settings)
    try:
        return await preflight(create_database_session_factory(engine),
            Target(args.recruiter_id, args.job_id, args.batch_id, args.upload_id), settings.cv_upload_root)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description='Privileged read-only maintenance preflight and manifest.')
    def identity(value):
        try:
            return UUID(value)
        except ValueError:
            raise argparse.ArgumentTypeError('A UUID is required; input withheld.') from None
    for key in ('recruiter-id', 'job-id', 'batch-id', 'upload-id'):
        parser.add_argument('--'+key, required=True, type=identity)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except Exception:
        result = dict(preflight=dict(state='unknown', deletion_ready=False),
                      error='preflight_unavailable', mutation_performed=False)
    print(json.dumps(result, sort_keys=True))
    # Manifest review is possible while maintenance remains blocked. No result
    # in this increment constitutes a successful exclusive-maintenance gate.
    return 2 if result['preflight']['state']=='unknown' else 1


if __name__ == '__main__':
    raise SystemExit(main())
