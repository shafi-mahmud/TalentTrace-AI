"""Private backend handoff contract. Never registered as an HTTP request schema."""
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.external_cv import SourceId,SubmissionId,ApplicationContact
from app.schemas.cv_upload import JobReference

class BridgeBinding(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    source_id:SourceId
    source_job_reference:JobReference
    recruiter_id:UUID
    target_job_id:UUID
    target_job_reference:JobReference

class ApplicationManifest(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,hide_input_in_errors=True)
    source_id:SourceId
    external_submission_id:SubmissionId
    source_job_reference:JobReference
    contact:ApplicationContact=Field(repr=False)
    content_type:Literal['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    size_bytes:int=Field(gt=0,le=10*1024*1024)
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$',repr=False)
    synthetic:Literal[True]=True
