"""Privileged administrative dry-run; configure DATABASE_URL privately."""
import argparse
import asyncio
import json
from uuid import UUID

from app.db.session import create_database_engine, create_database_session_factory
from app.core.config import settings
from app.services.candidate_inventory import Target, InventoryError, inventory


async def run(args):
    engine = create_database_engine(settings)
    try:
        async with create_database_session_factory(engine)() as session:
            return await inventory(session, Target(args.recruiter_id, args.job_id, args.batch_id, args.upload_id), settings.cv_upload_root)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description='Privileged count-only submission inventory; never deletes data.')
    def identity(value):
        try:
            return UUID(value)
        except ValueError:
            raise argparse.ArgumentTypeError('A UUID is required; input withheld.') from None
    for name in ('recruiter-id', 'job-id', 'batch-id', 'upload-id'):
        parser.add_argument('--' + name, type=identity, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except InventoryError as error:
        print(json.dumps({'error': str(error), 'mutation_performed': False}))
        return 1
    except Exception:
        # SQL/connection errors may contain private configuration. Do not print
        # exception objects or tracebacks from this administrative entry point.
        print(json.dumps({'error': 'inventory_unavailable', 'mutation_performed': False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
