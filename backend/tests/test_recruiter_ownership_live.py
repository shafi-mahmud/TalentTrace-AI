"""Opt-in real HTTP/PostgreSQL ownership proof against an isolated fixture server.

The server must use an isolated migrated database and synthetic provider fixtures;
publication remains disabled. Ordinary test runs skip this test and make no calls.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pymupdf
import pytest
from pydantic import SecretStr
from sqlalchemy import update
from sqlalchemy.engine import make_url

from app.core.auth import COOKIE_NAME, token_hash
from app.core.config import Settings, settings
from app.db.models.recruiter import RecruiterSession
from app.db.session import create_database_engine, create_database_session_factory

VERIFY_URL = os.getenv("TALENTTRACE_OWNERSHIP_VERIFY_URL")
VERIFY_DB = os.getenv("TALENTTRACE_OWNERSHIP_VERIFY_DATABASE")
pytestmark = pytest.mark.skipif(not VERIFY_URL or not VERIFY_DB, reason="Isolated ownership verification runtime not configured.")


def synthetic_pdf():
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 550, 700),
        "Synthetic demonstration CV. Not a real applicant.\nSkills: Python, FastAPI, PostgreSQL.\n"
        + "Built backend services and automated tests using documented engineering practices. " * 12)
    result = document.tobytes()
    document.close()
    return result


def test_real_database_http_ownership_persistence_and_shared_snapshots():
    assert VERIFY_URL.startswith("http://127.0.0.1:")
    assert VERIFY_DB.startswith("talenttrace_ownership_verify_")
    configuration = Settings(_env_file=None, database_url=SecretStr(
        make_url(settings.database_url.get_secret_value()).set(database=VERIFY_DB).render_as_string(hide_password=False)))
    async def scenario():
        engine = create_database_engine(configuration)
        factory = create_database_session_factory(engine)
        headers = {"X-TalentTrace-Request": "1"}
        try:
            async with httpx.AsyncClient(base_url=VERIFY_URL, headers=headers, timeout=30) as first, \
                       httpx.AsyncClient(base_url=VERIFY_URL, headers=headers, timeout=30) as second:
                assert (await first.get("/api/v1/jobs")).status_code == 401
                bad = await first.post("/api/v1/auth/login", json={"email": "ownership-a@example.test", "password": "wrong-synthetic"})
                assert bad.status_code == 401 and "wrong-synthetic" not in bad.text
                csrf = await first.post("/api/v1/auth/login", headers={"X-TalentTrace-Request": "", "Origin": "https://untrusted.example"},
                    json={"email": "ownership-a@example.test", "password": "synthetic-ownership-password-123"})
                assert csrf.status_code == 403
                for connection, email in ((first,"ownership-a@example.test"), (second,"ownership-b@example.test")):
                    response = await connection.post("/api/v1/auth/login", json={"email": email,"password": "synthetic-ownership-password-123"})
                    assert response.status_code == 200
                    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
                    assert set(response.json()) == {"id", "email"}
                    assert response.headers["cache-control"] == "no-store"
                message = "Create a Backend Engineer JD. Build and maintain secure backend services. Responsibilities: Develop APIs; Write tests. Required skills: Python and FastAPI. No minimum experience required."
                generated = await first.post("/api/v1/recruiter-chat",json={"message":message})
                assert generated.status_code == 200, "Isolated JD generation failed."
                reply = generated.json(); identity = reply["draft_id"]; conversation = reply["conversation_id"]
                assert reply["status"] == "jd_generated" and reply["job_description_result"]["human_review_required"] is True
                assert all(not c["is_hard"] for c in reply["screening_suggestions"]["criteria"])
                assert any(s["source"] == "company_policy" and s["citation_id"] for s in reply["screening_suggestion_sources"])
                job = next(j for j in (await first.get("/api/v1/jobs")).json() if j["id"] == identity)
                assert job["snapshot"] is None and job["job_reference"] == reply["job_reference"]
                assert identity not in {j["id"] for j in (await second.get("/api/v1/jobs")).json()}
                assert (await second.get(f"/api/v1/conversations/{conversation}")).status_code == 404
                assert (await second.post("/api/v1/recruiter-chat", json={"message":message,"conversation_id":conversation})).status_code == 404
                assert (await first.get(f"/api/v1/conversations/{conversation}")).status_code == 200
                repeat = await first.post("/api/v1/recruiter-chat",json={"message":message,"conversation_id":conversation})
                assert repeat.json()["status"] == "draft_unchanged", "Stored JSON state did not preserve unchanged generation."
                criteria = job["suggestions"]["criteria"]
                criteria[0]["is_hard"] = True
                update_body = {"revision":job["revision"],"confirmed":True,"criteria":criteria}
                assert (await second.put(f"/api/v1/jobs/{identity}/criteria",json=update_body)).status_code == 404
                approved = await first.put(f"/api/v1/jobs/{identity}/criteria",json=update_body)
                assert approved.status_code == 200
                snapshot = approved.json()["snapshot"]
                assert (await first.put(f"/api/v1/jobs/{identity}/criteria",json=update_body)).status_code == 409
                reference = job["job_reference"]
                cv = synthetic_pdf()
                uploaded = await first.post("/api/v1/cv-uploads",data={"job_reference":reference},files={"files":("synthetic.pdf",cv,"application/pdf")})
                assert uploaded.status_code == 201
                batch = uploaded.json(); path = f'/api/v1/cv-uploads/{reference}/{batch["batch_id"]}'
                denied = await second.post("/api/v1/cv-uploads",data={"job_reference":reference},files={"files":("synthetic.pdf",cv,"application/pdf")})
                assert denied.status_code == 404
                for suffix in ("extract","ocr","candidate-profiles"):
                    assert (await second.post(path+"/"+suffix)).status_code == 404
                assert (await second.post(path+"/screen",json=snapshot)).status_code == 404
                assert (await first.post(path+"/extract")).status_code == 200
                screened = await first.post(path+"/screen",json=snapshot)
                assert screened.status_code == 200
                result = screened.json()
                assert result["candidates"][0]["result"]["screening_decision"] == "eligible"
                assert result["ranking"][0]["supported_count"] == 2
                assert result["candidates"][0]["result"]["matching_result"]["matches"][0]["evidence"][0]["source"]["method"] == "digital"
                revised = await first.post("/api/v1/recruiter-chat",json={"message":"Also require Docker.","conversation_id":conversation})
                assert revised.status_code == 200 and revised.json()["draft_id"] == identity
                fresh = next(j for j in (await first.get("/api/v1/jobs")).json() if j["id"]==identity)
                assert fresh["snapshot"] is None and fresh["job_reference"] == reference
                assert (await first.post(path+"/screen",json=snapshot)).status_code == 409
                assert (await first.post(path+"/extract")).status_code == 200, "Material revision lost stored CV batch."
                reconfirm = await first.put(f"/api/v1/jobs/{identity}/criteria",json={"revision":fresh["revision"],"confirmed":True,"criteria":fresh["suggestions"]["criteria"]})
                assert reconfirm.status_code == 200
                assert (await first.post(path+"/screen",json=reconfirm.json()["snapshot"])).status_code == 200
                draft = revised.json()["job_description_result"]["job_description"]
                publication = {k:v for k,v in draft.items() if k != "policy_citation_ids"};publication["job_id"] = identity
                assert (await second.post("/api/v1/recruiter-chat/publish",json=publication)).status_code == 404
                assert (await first.post("/api/v1/recruiter-chat/publish",json={**publication,"summary":"Altered synthetic content"})).status_code == 409
                manual = await second.post("/api/v1/jobs",json={"job_title":"Independent synthetic manual job"})
                assert manual.status_code == 201 and manual.json()["snapshot"] is None
                async with factory() as session:
                    await session.execute(update(RecruiterSession).where(RecruiterSession.token_hash==token_hash(second.cookies.get(COOKIE_NAME))).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
                    await session.commit()
                assert (await second.get("/api/v1/jobs")).status_code == 401
                raw = first.cookies.get(COOKIE_NAME)
                assert (await first.post("/api/v1/auth/logout")).status_code == 200
                first.cookies.set(COOKIE_NAME,raw)
                assert (await first.get("/api/v1/jobs")).status_code == 401
        finally:
            await engine.dispose()
    asyncio.run(scenario())
