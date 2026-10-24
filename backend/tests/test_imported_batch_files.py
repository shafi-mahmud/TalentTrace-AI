"""Synthetic stored-file protections, no database/provider/network access."""
import hashlib
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from app.services.imported_batches import verify_files
from test_cv_extraction import pdf_bytes


def setup(tmp_path):
    job=N(id=uuid4(),job_reference='TT-JOB-AAAAAAAAAAAAAAAA')
    row=N(job_id=job.id,batch_id=uuid4(),upload_id=uuid4(),file_type='pdf',status='pending_review')
    data=pdf_bytes();root=tmp_path/job.job_reference/str(row.batch_id);root.mkdir(parents=True)
    path=root/(str(row.upload_id)+'.pdf');path.write_bytes(data)
    row.size_bytes=len(data);row.content_sha256=hashlib.sha256(data).hexdigest()
    return job,row,path


def test_exact_trusted_set_accepts_valid_file(tmp_path):
    job,row,path=setup(tmp_path);verify_files(tmp_path,job,[row])


@pytest.mark.parametrize('change',['foreign_job','invalid_status','duplicate_identity','extra_file','missing','size','digest','signature'])
def test_unavailable_files_and_associations_fail_closed(tmp_path,change):
    job,row,path=setup(tmp_path);rows=[row]
    if change=='foreign_job':row.job_id=uuid4()
    elif change=='invalid_status':row.status='unexpected'
    elif change=='duplicate_identity':rows.append(row)
    elif change=='extra_file':path.with_name(str(uuid4())+'.pdf').write_bytes(path.read_bytes())
    elif change=='missing':path.unlink()
    elif change=='size':row.size_bytes+=1
    elif change=='digest':row.content_sha256='0'*64
    elif change=='signature':path.write_bytes(b'X'*row.size_bytes)
    with pytest.raises(Exception):verify_files(tmp_path,job,rows)
