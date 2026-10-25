"""Encrypted, bounded synthetic-reference vault. Not production biometric storage."""
from contextlib import contextmanager
from dataclasses import asdict
import base64
try:
    import fcntl
except ImportError:
    fcntl=None
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION='synthetic-face-workflow-v1'
WORDING=('Optional artificial-face demonstration. Only server-generated synthetic samples are used. '
         'The encrypted synthetic reference is retained until the displayed expiry, unless withdrawn or deleted earlier. '
         'This consent is separate from captions, transcript storage and assistant processing. '
         'No real biometric enrollment, identity certification, liveness or hiring decision is enabled. '
         'You may decline and request manual, non-biometric review. Retain your withdrawal receipt or ask the recruiter to delete the reference.')

class VaultError(ValueError):pass


def scope_dict(binding):return {k:str(v) if k!='criteria_revision' else v for k,v in asdict(binding).items()}

class FaceVault:
    def __init__(self,root,key,retention_seconds,clock=time.time):
        self.root=Path(root);self.clock=clock
        if fcntl is None:raise VaultError("unsupported_platform")
        if not 60<=retention_seconds<=604800:raise VaultError('configuration_unavailable')
        self.retention=retention_seconds
        try:
            raw=base64.urlsafe_b64decode(key)
            if len(raw)!=32:raise ValueError()
            self.cipher=AESGCM(raw)
            if self.root.is_symlink() or not self.root.is_dir() or self.root.stat().st_mode & 0o077:raise ValueError()
        except Exception:raise VaultError('configuration_unavailable') from None

    @contextmanager
    def locked(self):
        fd=os.open(self.root/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            if os.fstat(fd).st_mode & 0o077:raise VaultError('unsafe_storage')
            fcntl.flock(fd,fcntl.LOCK_EX);yield
        finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

    def path(self,interview):
        from uuid import UUID
        return self.root/(str(UUID(str(interview)))+'.sealed')
    def aad(self,interview):return (VERSION+':'+str(interview)).encode()
    def _load(self,interview):
        p=self.path(interview)
        try:
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as stream:
                if os.fstat(stream.fileno()).st_mode & 0o077:raise ValueError()
                data=stream.read(32769)
            if not 28<len(data)<=32768:raise ValueError()
            row=json.loads(self.cipher.decrypt(data[:12],data[12:],self.aad(interview)))
            if row['version']!=VERSION:raise ValueError()
            if row['expires_at']<=self.clock():p.unlink();raise VaultError('reference_expired')
            return row
        except FileNotFoundError:raise VaultError('reference_unavailable') from None
        except VaultError:raise
        except Exception:raise VaultError('reference_restricted') from None
    def _write(self,interview,row):
        nonce=os.urandom(12);data=nonce+self.cipher.encrypt(nonce,json.dumps(row,allow_nan=False).encode(),self.aad(interview))
        temp=self.root/('.'+str(interview)+'.'+secrets.token_hex(8)+'.tmp')
        try:
            fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            os.replace(temp,self.path(interview))
            fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:temp.unlink(missing_ok=True)
    def _checked(self,binding,run_id=None):
        row=self._load(binding.interview_id)
        if row['scope']!=scope_dict(binding):raise VaultError('source_changed')
        if run_id and row['run_id']!=str(run_id):raise VaultError('run_changed')
        if row['state']=='withdrawn':raise VaultError('consent_withdrawn')
        return row
    def consent(self,binding,identity):
        if identity not in ('a','c'):raise VaultError('synthetic_identity_required')
        token=secrets.token_urlsafe(32)
        with self.locked():
            if self.path(binding.interview_id).exists():
                try:self._load(binding.interview_id)
                except VaultError as error:
                    if str(error)!='reference_expired':raise
                else:raise VaultError('consent_already_recorded')
            if len(list(self.root.glob('*.sealed')))>=32:raise VaultError('capacity_unavailable')
            now=self.clock();row=dict(version=VERSION,scope=scope_dict(binding),run_id=str(uuid4()),identity=identity,
                state='consented',consented_at=now,expires_at=now+self.retention,withdrawal_hash=hashlib.sha256(token.encode()).hexdigest(),
                feature=None,provenance=None,audit=[{'event':'consented','at':now}])
            self._write(binding.interview_id,row)
            return {**self.public(row),'withdrawal_receipt':token}
    def public(self,row):
        return {'state':row['state'],'run_id':row['run_id'],'expires_at':row['expires_at'],'consent_version':VERSION,
                'synthetic_only':True,'human_review_required':True}
    def read(self,binding,run_id=None):
        with self.locked():return self._checked(binding,run_id)
    def enroll(self,binding,run_id,feature,provenance):
        if len(feature)!=128 or not all(math.isfinite(v) for v in feature):raise VaultError('invalid_feature')
        from app.integrations.face.metrics import cosine_similarity
        cosine_similarity(feature,feature)
        with self.locked():
            row=self._checked(binding,run_id)
            if row['state']!='consented':raise VaultError('reference_already_enrolled')
            row.update(state='enrolled',feature=list(feature),provenance=provenance)
            row['audit'].append({'event':'enrolled','at':self.clock()});self._write(binding.interview_id,row)
            return self.public(row)
    def compare(self,binding,run_id,feature):
        from app.integrations.face.metrics import cosine_similarity
        with self.locked():
            row=self._checked(binding,run_id)
            if row['state']!='enrolled':raise VaultError('reference_not_enrolled')
            score=cosine_similarity(row['feature'],feature)
            row['audit']=(row['audit']+[{'event':'compared','at':self.clock()}])[-16:]
            self._write(binding.interview_id,row)
            return {'similarity':round(score,8),'provisional':True,'human_review_required':True,
                    'identity_verified':False,'liveness_checked':False,'synthetic_only':True,'decision':'no_automated_decision'}
    def withdraw_authorized(self,binding,run_id):
        with self.locked():
            row=self._checked(binding,run_id)
            row.update(state='withdrawn',feature=None,provenance=None)
            row['audit']=[{'event':'withdrawn','at':self.clock()}];self._write(binding.interview_id,row)
    def withdraw(self,interview,token):
        with self.locked():
            row=self._load(interview)
            if not hmac.compare_digest(row['withdrawal_hash'],hashlib.sha256(token.encode()).hexdigest()):raise VaultError('withdrawal_denied')
            row.update(state='withdrawn',feature=None,provenance=None)
            row['audit']=[{'event':'withdrawn','at':self.clock()}];self._write(interview,row)
    def delete(self,interview):
        with self.locked():self.path(interview).unlink(missing_ok=True)
    def cleanup(self):
        with self.locked():
            for p in list(self.root.glob('*.sealed'))[:32]:
                try:self._load(p.stem)
                except VaultError:pass # Integrity/key failures require operator review; never overwrite.
            # Recover expired encrypted temp files left by a process crash mid-atomic-write.
            import re
            for p in list(self.root.glob('.*.tmp'))[:64]:
                m=re.fullmatch(r'\.([0-9a-f-]{36})\.[0-9a-f]{16}\.tmp',p.name)
                if not m or p.is_symlink():continue
                try:
                    data=p.read_bytes()
                    if len(data)>32768:continue
                    row=json.loads(self.cipher.decrypt(data[:12],data[12:],self.aad(m[1])))
                    if row['expires_at']<=self.clock():p.unlink()
                except Exception:pass
            # Only remove abandoned synthetic worker trees when no worker holds the slot.
            fd=os.open(self.root/'.worker',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            try:
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return
                import shutil
                for p in list(self.root.glob('worker-*'))[:32]:
                    if p.is_dir() and not p.is_symlink() and self.clock()-p.stat().st_mtime>60:shutil.rmtree(p)
            finally:os.close(fd)
