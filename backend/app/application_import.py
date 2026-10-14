"""Explicit local operator import; fixed private configuration, never startup sync."""
import argparse,asyncio,json,os,stat,subprocess
from pathlib import Path
from pydantic import BaseModel,ConfigDict,SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.config import REPOSITORY_ROOT
from app.services.intake_reader import TrustedIntakeReader,IntakeBinding
from app.services.application_bridge import ApplicationImportBridge,ApplicationBridgeError
from app.services.external_cv import ExternalCvImportError
from app.services.cv_upload import CvUploadError

class OperatorConfiguration(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    source_database_url:SecretStr
    target_database_url:SecretStr
    source_storage_root:Path
    target_storage_root:Path
    binding:IntakeBinding

def private_file(path):
    if not path.is_file() or path.stat().st_size>32768:return False
    if any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)):return False
    if os.name!='nt':return stat.S_IMODE(path.stat().st_mode)&0o077==0
    script="$ErrorActionPreference='Stop';$allowed=@([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18','S-1-5-32-544');foreach($p in @($env:TT_BRIDGE_CONFIG,(Split-Path -LiteralPath $env:TT_BRIDGE_CONFIG))){foreach($r in (Get-Acl -LiteralPath $p).Access){if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -notin $allowed){exit 1}}};exit 0"
    try:
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',script],env={**os.environ,'TT_BRIDGE_CONFIG':str(path)},capture_output=True,timeout=10)
        return result.returncode==0
    except Exception:return False

def load_configuration():
    path=REPOSITORY_ROOT/'data'/'application_bridge'/'configuration.json'
    if not private_file(path):raise ApplicationBridgeError('bridge_configuration_not_private')
    if subprocess.run(['git','check-ignore','-q',str(path)],cwd=REPOSITORY_ROOT,capture_output=True).returncode!=0:
        raise ApplicationBridgeError('bridge_configuration_not_ignored')
    tracked=subprocess.run(['git','ls-files','--',str(path)],cwd=REPOSITORY_ROOT,capture_output=True)
    if tracked.returncode!=0 or tracked.stdout:raise ApplicationBridgeError('bridge_configuration_tracked')
    value=OperatorConfiguration.model_validate_json(path.read_text())
    for secret,port,database in [(value.source_database_url,54379,'talenttrace_external_intake'),(value.target_database_url,54378,'talenttrace_f4_local')]:
        url=make_url(secret.get_secret_value())
        if url.drivername!='postgresql+asyncpg' or url.host!='127.0.0.1' or url.port!=port or url.database!=database or url.query:
            raise ApplicationBridgeError('bridge_database_identity_mismatch')
    if not value.source_storage_root.is_absolute() or not value.target_storage_root.is_absolute():
        raise ApplicationBridgeError('bridge_storage_configuration_invalid')
    source=value.source_storage_root.resolve()
    target=value.target_storage_root.resolve()
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ApplicationBridgeError('bridge_storage_roots_overlap')
    return value

async def execute(configuration,submission_id):
    source=create_async_engine(configuration.source_database_url.get_secret_value(),hide_parameters=True)
    target=create_async_engine(configuration.target_database_url.get_secret_value(),hide_parameters=True)
    try:
        reader=TrustedIntakeReader(async_sessionmaker(source,expire_on_commit=False),configuration.source_storage_root,configuration.binding)
        bridge=ApplicationImportBridge(async_sessionmaker(target,expire_on_commit=False),configuration.target_storage_root,(configuration.binding.target,),reader)
        async with asyncio.timeout(30):
            result=await bridge.import_application(configuration.binding.target.recruiter_id,configuration.binding.target.source_id,submission_id)
        return {'imported':result.created,'reused':not result.created,'status':result.status,'screened':False}
    finally:
        await source.dispose();await target.dispose()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--submission',required=True);parser.add_argument('--confirm-synthetic-import',action='store_true')
    args=parser.parse_args()
    try:
        if not args.confirm_synthetic_import:raise ApplicationBridgeError('confirmation_required')
        print(json.dumps(asyncio.run(execute(load_configuration(),args.submission))));return 0
    except (ApplicationBridgeError,ExternalCvImportError,CvUploadError) as error:print(json.dumps({'code':error.code}));return 1
    except Exception:print('{"code":"application_import_failed"}');return 1
if __name__=='__main__':raise SystemExit(main())
