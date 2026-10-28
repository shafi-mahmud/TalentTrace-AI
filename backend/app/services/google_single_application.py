"""One owner-approved Google response, adapted from the existing intake validators.
No credentials, network I/O, database writes, paging or implicit source routing.
"""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

CUTOFF = "2026-10-16T00:00:00Z"
MAX_BYTES = 10 * 1024 * 1024
MIMES = {"application/pdf": "pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}

class SingleApplicationError(ValueError):
    """Fixed categories only, never response contents or identifiers."""

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",value):
        raise SingleApplicationError("invalid_identity")
    return value

def responses_url(form_id):
    return "https://forms.googleapis.com/v1/forms/"+identifier(form_id)+"/responses?"+urlencode({
        "filter":"timestamp > "+CUTOFF,"pageSize":1,
        "fields":"responses(responseId,createTime,lastSubmittedTime,respondentEmail,answers),nextPageToken"})

def text_answer(answers,key):
    row=answers.get(key,{})
    items=row.get("textAnswers",{}).get("answers",[])
    if row.get("questionId")!=key or "fileUploadAnswers" in row or len(items)!=1 or not isinstance(items[0].get("value"),str):
        raise SingleApplicationError("invalid_answer")
    return items[0]["value"].strip()

def select_response(page,config):
    rows=page.get("responses")
    if "nextPageToken" in page or not isinstance(rows,list) or len(rows)!=1:
        raise SingleApplicationError("ambiguous_response")
    row=rows[0];response_id=identifier(row.get("responseId"))
    try:
        created=datetime.fromisoformat(row["createTime"].replace("Z","+00:00"))
        submitted=datetime.fromisoformat(row["lastSubmittedTime"].replace("Z","+00:00"))
        if (created.tzinfo is None or submitted.tzinfo is None or created<=datetime.fromisoformat(CUTOFF.replace("Z","+00:00"))
            or submitted<created or submitted.timestamp()>datetime.now(timezone.utc).timestamp()+60):raise ValueError()
    except Exception:raise SingleApplicationError("outside_approved_window") from None
    answers=row.get("answers")
    if not isinstance(answers,dict) or len(answers)>50:raise SingleApplicationError("invalid_answer")
    if text_answer(answers,config["job_question_id"])!=config["job_reference"]:raise SingleApplicationError("wrong_job")
    if text_answer(answers,config["consent_question_id"])!=config["expected_consent"]:raise SingleApplicationError("consent_missing")
    # The exact owner-approved synthetic name must occur once in a text answer.
    names=[a.get("textAnswers",{}).get("answers",[]) for a in answers.values()]
    if sum(len(v)==1 and v[0].get("value","").strip()==config["candidate_name"] for v in names)!=1:
        raise SingleApplicationError("synthetic_identity_mismatch")
    cv=answers.get(config["cv_question_id"],{})
    files=cv.get("fileUploadAnswers",{}).get("answers",[])
    if cv.get("questionId")!=config["cv_question_id"] or "textAnswers" in cv or len(files)!=1:
        raise SingleApplicationError("single_cv_required")
    file=files[0];file_id=identifier(file.get("fileId"));mime=file.get("mimeType")
    if mime not in MIMES:raise SingleApplicationError("unsafe_file_type")
    key="gform_"+hashlib.sha256((identifier(config["form_id"])+"\0"+response_id).encode()).hexdigest()
    return row,key,file_id,mime

def validate_metadata(meta,file_id,mime,folder):
    try:
        size=meta["size"]
        if (meta["id"]!=file_id or meta["mimeType"]!=mime or meta["trashed"] is not False
            or meta.get("capabilities",{}).get("canDownload") is not True or folder not in meta["parents"]
            or not isinstance(size,str) or not size.isdigit() or not 0<int(size)<=MAX_BYTES
            or not re.fullmatch(r"[a-f0-9]{32}",meta["md5Checksum"])):raise ValueError()
        return int(size)
    except Exception:raise SingleApplicationError("invalid_file_metadata") from None

def validate_bytes(data,meta,mime):
    if (len(data)!=int(meta["size"]) or len(data)>MAX_BYTES
        or hashlib.md5(data,usedforsecurity=False).hexdigest()!=meta["md5Checksum"]
        or not data.startswith(b"%PDF-" if mime=="application/pdf" else b"PK\x03\x04")):
        raise SingleApplicationError("file_integrity_failed")
    return hashlib.sha256(data).hexdigest()
