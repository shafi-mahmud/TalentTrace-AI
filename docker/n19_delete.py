"""Administrative exact-import deletion; only the existing isolated N19 lab."""
import argparse
import json
from pathlib import Path
from uuid import UUID
import n19_lab


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preview','execute','status'])
    parser.add_argument('--state',required=True,type=Path)
    for name in ('recruiter-id','job-id','batch-id','upload-id'):
        def identity(value):
            try:return UUID(value)
            except ValueError:raise argparse.ArgumentTypeError('UUID required; value withheld') from None
        parser.add_argument('--'+name,required=True,type=identity)
    parser.add_argument('--expect-digest')
    parser.add_argument('--confirm-exact-submission',action='store_true')
    args=parser.parse_args()
    if args.action=='execute' and (not args.confirm_exact_submission or not args.expect_digest or len(args.expect_digest)!=64):
        parser.error('Explicit exact-submission confirmation and preview digest required')
    try:
        lab=n19_lab.load(args.state);n19_lab.check(lab)
        target=[str(getattr(args,k)) for k in ('recruiter_id','job_id','batch_id','upload_id')]
        code=f'''import asyncio,json
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.config import settings
from app.services.candidate_inventory import Target
from app.services.submission_deletion import preview,delete_submission,deletion_status
from uuid import UUID
async def run():
 e=create_async_engine(settings.database_url.get_secret_value(),poolclass=NullPool,hide_parameters=True)
 try:
  f=async_sessionmaker(e);t=Target(*map(UUID,{target!r}))
  result=await {"preview(f,t,settings.cv_upload_root)" if args.action=='preview' else "deletion_status(f,t,settings.cv_upload_root)" if args.action=='status' else "delete_submission(f,t,settings.cv_upload_root,"+repr(args.expect_digest)+")"}
  print(json.dumps(result,sort_keys=True))
 finally:await e.dispose()
asyncio.run(run())
'''
        result=n19_lab.worker(lab,code,check=False)
        if result.returncode:raise RuntimeError('deletion_blocked')
        print(result.stdout.strip());return 0
    except Exception:
        print(json.dumps(dict(state='blocked_or_incomplete',maintenance='remains_closed',action='inspect_journal_then_retry_same_target')))
        return 1


if __name__=='__main__':raise SystemExit(main())
