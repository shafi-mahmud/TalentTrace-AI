"""Optional actual-model subprocess; no browser sample bytes, URLs or embeddings."""
import asyncio,json,os
try:
    import fcntl
except ImportError:
    fcntl=None
from tempfile import TemporaryDirectory
from pathlib import Path
from app.core.config import REPOSITORY_ROOT,settings
from app.services.face_vault import FaceVault,VaultError

worker_lock=asyncio.Lock()

def vault(require_enabled=True):
    c=settings
    if require_enabled and not c.face_workflow_enabled:raise VaultError('workflow_disabled')
    if not c.face_workflow_root or not c.face_workflow_key or c.face_workflow_retention_seconds is None:raise VaultError('configuration_unavailable')
    root=c.face_workflow_root.resolve()
    if not root.is_relative_to((REPOSITORY_ROOT/'data').resolve()) or c.face_workflow_root.is_symlink():raise VaultError('unsafe_storage')
    return FaceVault(root,c.face_workflow_key.get_secret_value(),c.face_workflow_retention_seconds)

async def feature(identity,probe):
    c=settings
    if fcntl is None:raise VaultError("unsupported_platform")
    if not c.face_workflow_enabled or not c.face_workflow_python or not c.face_workflow_models:raise VaultError('models_unavailable')
    if worker_lock.locked():raise VaultError('worker_busy')
    async with worker_lock:
        process=None;slot=None;directory=None
        try:
            root=vault().root
            slot=os.open(root/'.worker',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
            directory=TemporaryDirectory(prefix='worker-',dir=root)
            process=await asyncio.create_subprocess_exec(str(c.face_workflow_python),'-B',str(REPOSITORY_ROOT/'backend/scripts/face_feature_worker.py'),
                str(c.face_workflow_models),directory.name,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(REPOSITORY_ROOT/'backend'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
            output,_=await asyncio.wait_for(process.communicate(json.dumps({'identity':identity,'probe':probe}).encode()),20)
            if process.returncode or len(output)>16384:raise ValueError()
            result=json.loads(output)
            if set(result)!={'feature','provenance'} or len(result['feature'])!=128 or result['provenance']['source']!='server_generated_geometry':raise ValueError()
            return result
        except (Exception,):raise VaultError('synthetic_sample_unavailable') from None
        finally:
            if process and process.returncode is None:process.kill();await process.wait()
            if directory:directory.cleanup()
            if slot is not None:os.close(slot)

async def maintenance_loop():
    while True:
        try:
            c=settings
            # Cleanup continues when disabled if the operator retains the vault/key configuration.
            if c.face_workflow_root and c.face_workflow_key and c.face_workflow_retention_seconds:
                store=vault(False)
                await asyncio.to_thread(store.cleanup)
        except (VaultError,OSError):pass
        await asyncio.sleep(30)
