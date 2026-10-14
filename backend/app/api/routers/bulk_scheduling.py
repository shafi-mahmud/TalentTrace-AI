"""Authenticated job-cohort preview, explicit confirmation and saved status."""
from uuid import UUID
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.core.auth import current_recruiter,database_session
from app.core.config import settings
from app.services import bulk_scheduling as service
router=APIRouter(tags=['Bulk scheduling'])
class Empty(BaseModel):model_config=ConfigDict(extra='forbid')
class Approval(Empty):
    operation_id:UUID
    confirmed:bool=Field(strict=True)
    @field_validator("confirmed")
    @classmethod
    def approved(cls,value):
        if value is not True:raise ValueError("Explicit approval required")
        return value
@router.post('/jobs/{job_id}/bulk-scheduling/preview')
async def preview(job_id:UUID,body:Empty,request:Request,user=Depends(current_recruiter),session=Depends(database_session)):
    return await service.preview(session,user.id,job_id,request.headers.get('x-talenttrace-job-revision'),settings)
@router.post('/jobs/{job_id}/bulk-scheduling/send')
async def send(job_id:UUID,body:Approval,request:Request,user=Depends(current_recruiter),session=Depends(database_session)):
    return await service.send(session,user.id,job_id,body.operation_id,request.headers.get('x-talenttrace-job-revision'),settings)
@router.get('/jobs/{job_id}/bulk-scheduling/operations/{operation_id}')
async def status(job_id:UUID,operation_id:UUID,user=Depends(current_recruiter),session=Depends(database_session)):
    return await service.status_reply(session,await service.operation(session,user.id,job_id,operation_id))
