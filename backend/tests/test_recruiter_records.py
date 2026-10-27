"""Security/API integration with a transactional session double, not live PostgreSQL.

Only SQL execution is substituted. Real auth, ownership, routes, schemas and chat
orchestration run; no current_recruiter override and no provider/network calls.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BindParameter, BinaryExpression, BooleanClauseList, True_, False_

from app.core.auth import COOKIE_NAME, database_session, hash_password, token_hash, verify_password
from app.db.models.recruiter import Recruiter, RecruiterSession, RecruiterConversation, ChatTurn, JobProfile
from app.main import app
from app.api.routers import auth, recruiter_chat
from app.schemas.recruiter_chat import RecruiterChatRequest, RecruiterInterpretation
from app.services.recruiter_records import encode_conversation, restore_conversation, private_settings
from app.services.recruiter_chat import _Conversation, _GroundedItem

TABLES = {model.__tablename__: model for model in (Recruiter, RecruiterSession, RecruiterConversation, ChatTurn, JobProfile)}


class SessionDouble:
    def __init__(self, database):
        self.database = database
        self.rows = deepcopy(database)

    def add(self, row):
        if hasattr(row, "id") and row.id is None:
            row.id = uuid4()
        self.rows.setdefault(type(row), []).append(row)

    async def flush(self):
        pass

    async def commit(self):
        self.database.clear()
        self.database.update(deepcopy(self.rows))

    def value(self, expr, context):
        if isinstance(expr, BindParameter): return expr.value
        if isinstance(expr, True_): return True
        if isinstance(expr, False_): return False
        if isinstance(expr, BooleanClauseList): return all(self.value(item, context) for item in expr.clauses)
        if isinstance(expr, BinaryExpression):
            left, right = self.value(expr.left, context), self.value(expr.right, context)
            if expr.operator in (operators.eq, operators.is_): return left == right
            if expr.operator is operators.gt: return left > right
            if expr.operator is operators.lt: return left < right
            raise AssertionError("Unimplemented test SQL operator")
        return getattr(context[expr.table.name], expr.name)

    def selected(self, query):
        entity = query.column_descriptions[0].get("entity")
        if entity is None:
            # The only aggregate is the persisted chat-turn sequence count.
            entity = ChatTurn
        contexts = [{entity.__tablename__: row} for row in self.rows.get(entity, [])]
        if entity is Recruiter and "JOIN recruiter_sessions" in str(query):
            contexts = [{**ctx, "recruiter_sessions": token} for ctx in contexts
                for token in self.rows.get(RecruiterSession, []) if ctx["recruiters"].id == token.recruiter_id]
        contexts = [ctx for ctx in contexts if all(self.value(clause, ctx) for clause in query._where_criteria)]
        return entity, contexts

    async def scalar(self, query):
        entity, contexts = self.selected(query)
        if query.column_descriptions[0].get("entity") is None: return len(contexts)
        return contexts[0][entity.__tablename__] if contexts else None

    async def scalars(self, query):
        entity, contexts = self.selected(query)
        rows = [ctx[entity.__tablename__] for ctx in contexts]
        if entity is ChatTurn: rows.sort(key=lambda row: row.sequence)
        return SimpleNamespace(all=lambda: rows)

    async def execute(self, query):
        if getattr(query, 'is_select', False):
            from collections import namedtuple
            entity, contexts = self.selected(query)
            names = [column['name'] for column in query.column_descriptions]
            Projection = namedtuple('Projection', names)
            return SimpleNamespace(all=lambda: [Projection(*(getattr(ctx[entity.__tablename__], name) for name in names)) for ctx in contexts])
        entity = TABLES[query.table.name]
        self.rows[entity] = [row for row in self.rows.get(entity, []) if not all(
            self.value(clause, {entity.__tablename__: row}) for clause in query._where_criteria)]


@pytest.fixture
def workspace(monkeypatch):
    # Synthetic, non-production credentials only; not logged by tests.
    password = "synthetic-test-password-123"
    encoded = hash_password(password)
    users = [Recruiter(id=uuid4(), email=f"recruiter-{n}@example.test", password_hash=encoded, active=True) for n in (1, 2)]
    db = {Recruiter: users}
    async def session():
        yield SessionDouble(db)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[database_session] = session
    auth._attempts.clear()
    # Provider use is always a test failure unless a test installs a structured fake.
    monkeypatch.setattr(recruiter_chat, "get_recruiter_interpreter", lambda: pytest.fail("Unexpected provider use"))
    yield db, users, password
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    auth._attempts.clear()


def run(task):
    return asyncio.run(task)


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                            headers={"X-TalentTrace-Request": "1", "Origin": "http://test"})


async def login(connection, user, password):
    response = await connection.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200
    return response


def test_login_cookie_logout_and_no_token_disclosure(workspace):
    db, users, password = workspace
    async def scenario():
        async with client() as connection:
            assert (await connection.get("/api/v1/jobs")).status_code == 401
            response = await login(connection, users[0], password)
            cookie = response.headers["set-cookie"]
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie
            assert set(response.json()) == {"id", "email"}
            raw = connection.cookies.get(COOKIE_NAME)
            assert db[RecruiterSession][0].token_hash == token_hash(raw)
            assert raw not in db[RecruiterSession][0].token_hash
            assert (await connection.get("/api/v1/auth/me")).status_code == 200
            assert (await connection.post("/api/v1/auth/logout")).status_code == 200
            connection.cookies.set(COOKIE_NAME, raw)
            assert (await connection.get("/api/v1/jobs")).status_code == 401
    run(scenario())


def test_cookie_expiry_inactive_user_and_bad_password(workspace):
    db, users, password = workspace
    async def scenario():
        async with client() as connection:
            bad = await connection.post("/api/v1/auth/login", json={"email": users[0].email, "password": "wrong"})
            assert bad.status_code == 401 and "wrong" not in bad.text
            await login(connection, users[0], password)
            db[RecruiterSession][0].expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            assert (await connection.get("/api/v1/jobs")).status_code == 401
            await login(connection, users[0], password)
            db[Recruiter][0].active = False
            assert (await connection.get("/api/v1/jobs")).status_code == 401
    run(scenario())


@pytest.mark.parametrize("headers", [{"X-TalentTrace-Request": ""}, {"Origin": "https://untrusted.example"}, {"Origin": "null"}])
def test_csrf_rejected_before_login(workspace, headers):
    _, users, password = workspace
    async def scenario():
        async with client() as connection:
            response = await connection.post("/api/v1/auth/login", headers=headers, json={"email": users[0].email, "password": password})
            assert response.status_code == 403
    run(scenario())


def test_login_throttle_and_bounded_input(workspace):
    _, users, _ = workspace
    async def scenario():
        async with client() as connection:
            large = await connection.post("/api/v1/auth/login", json={"email": users[0].email, "password": "x"*129})
            assert large.status_code == 422 and "x"*129 not in large.text
            for _ in range(5):
                assert (await connection.post("/api/v1/auth/login", json={"email": users[0].email, "password": "wrong"})).status_code == 401
            assert (await connection.post("/api/v1/auth/login", json={"email": users[0].email, "password": "wrong"})).status_code == 429
    run(scenario())


def test_owned_jobs_confirmation_stale_revision_and_foreign_access(workspace):
    _, users, password = workspace
    async def scenario():
        async with client() as first, client() as second:
            await login(first, users[0], password)
            await login(second, users[1], password)
            created = await first.post("/api/v1/jobs", json={"job_title": "Synthetic Engineer"})
            assert created.status_code == 201
            job = created.json()
            assert job["snapshot"] is None and job["job_reference"].startswith("TT-JOB-")
            assert (await second.get("/api/v1/jobs")).json() == []
            update = {"revision": 1, "confirmed": True, "criteria": [{"criterion_id": "python", "description": "Python", "category": "skill", "is_hard": False}]}
            assert (await second.put(f'/api/v1/jobs/{job["id"]}/criteria', json=update)).status_code == 404
            assert (await first.put(f'/api/v1/jobs/{job["id"]}/criteria', json={**update, "confirmed": "true"})).status_code == 422
            approved = await first.put(f'/api/v1/jobs/{job["id"]}/criteria', json=update)
            assert approved.status_code == 200 and approved.json()["snapshot"]["criteria_confirmed"] is True
            assert (await first.put(f'/api/v1/jobs/{job["id"]}/criteria', json=update)).status_code == 409
            edited = await first.put(f'/api/v1/jobs/{job["id"]}/criteria', json={**update, "revision": 2, "confirmed": False})
            assert edited.json()["snapshot"] is None
            assert (await second.post(f'/api/v1/cv-uploads/{job["job_reference"]}/{uuid4()}/extract')).status_code == 404
    run(scenario())


def test_conversation_roundtrip_preserves_grounded_zero_experience():
    item = _Conversation(conversation_id=uuid4(), messages=["No minimum experience required."],
        requirements={"minimum_experience_years": [_GroundedItem(0, "No minimum experience required.")]}, last_asked_field="required_skills")
    restored = restore_conversation(SimpleNamespace(id=item.conversation_id, state=encode_conversation(item)))
    assert restored.requirements["minimum_experience_years"][0].value == 0
    assert restored.last_asked_field == "required_skills"
    assert restored.messages == item.messages


def test_password_hash_and_private_roots():
    encoded = hash_password("synthetic-password-long")
    assert verify_password("synthetic-password-long", encoded)
    assert not verify_password("different", encoded)
    assert not verify_password("different", "invalid")
    first, second = uuid4(), uuid4()
    one = private_settings(SimpleNamespace(state=SimpleNamespace(recruiter_id=first)))
    two = private_settings(SimpleNamespace(state=SimpleNamespace(recruiter_id=second)))
    assert one.cv_upload_root != two.cv_upload_root
    assert one.cv_upload_root.name == str(first)


def install_chat(monkeypatch, *, error=None):
    from test_recruiter_chat import FakeInterpreter, RecordingWorkflow
    from app.services.recruiter_chat import RecruiterChatService
    workflow = RecordingWorkflow(error=error)
    monkeypatch.setattr(recruiter_chat, "get_recruiter_interpreter", FakeInterpreter)
    monkeypatch.setattr(recruiter_chat, "RecruiterChatService", lambda interpreter:
                        RecruiterChatService(interpreter, workflow_factory=lambda: workflow))
    return workflow


def test_chat_persists_restores_and_isolates_owners_across_requests(workspace, monkeypatch):
    from test_recruiter_chat import MESSAGE
    db, users, password = workspace
    workflow = install_chat(monkeypatch)
    async def scenario():
        async with client() as first, client() as second:
            await login(first, users[0], password)
            await login(second, users[1], password)
            response = await first.post("/api/v1/recruiter-chat", json={"message": MESSAGE})
            assert response.status_code == 200
            reply = response.json()
            identity = reply["conversation_id"]
            job = (await first.get("/api/v1/jobs")).json()[0]
            assert job["id"] == reply["draft_id"] and job["job_reference"] == reply["job_reference"]
            assert job["snapshot"] is None and job["revision"] == 1
            assert len(db[ChatTurn]) == len(db[JobProfile]) == len(db[RecruiterConversation]) == 1
            saved_reply = (await first.get(f"/api/v1/conversations/{identity}")).json()["turns"][0]["reply"]
            from app.schemas.recruiter_chat import RecruiterChatResponse
            from pydantic import TypeAdapter
            adapter = TypeAdapter(RecruiterChatResponse)
            assert adapter.validate_python(saved_reply) == adapter.validate_python(reply)
            assert (await first.get(f"/api/v1/conversations/{identity}")).json()['ai_provider'] == 'groq'
            record = db[RecruiterConversation][0]
            record.state = {**record.state,'ai_provider':'ollama:qwen2.5:1.5b'}
            assert (await first.get(f"/api/v1/conversations/{identity}")).json()['ai_provider'] == 'ollama:qwen2.5:1.5b'
            record.state = {**record.state,'ai_provider':'unrecognized-private-value'}
            bad = await first.get(f"/api/v1/conversations/{identity}")
            assert bad.status_code == 500 and 'unrecognized-private-value' not in bad.text
            record.state = {**record.state,'ai_provider':'groq'}
            assert (await second.get("/api/v1/conversations")).json() == []
            assert (await second.get(f"/api/v1/conversations/{identity}")).status_code == 404
            assert (await second.post("/api/v1/recruiter-chat", json={"message": MESSAGE, "conversation_id": identity})).status_code == 404
            # A fresh request/session rehydrates server state; duplicate successful input
            # does not repeat JD generation or create another persistent job.
            repeated = await first.post("/api/v1/recruiter-chat", json={"message": MESSAGE, "conversation_id": identity})
            assert repeated.json()["status"] == "draft_unchanged"
            assert len(workflow.requests) == 1 and len(db[JobProfile]) == 1 and len(db[ChatTurn]) == 2
            db[RecruiterConversation][0].expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            assert (await first.post("/api/v1/recruiter-chat", json={"message": MESSAGE, "conversation_id": identity})).status_code == 409
            assert len(db[ChatTurn]) == 2
    run(scenario())


def test_chat_failure_does_not_persist_partial_conversation_or_private_error(workspace, monkeypatch):
    from test_recruiter_chat import MESSAGE
    from app.agents.jd.errors import GenerationProviderError
    db, users, password = workspace
    install_chat(monkeypatch, error=GenerationProviderError("PRIVATE_PROVIDER_DETAIL"))
    async def scenario():
        async with client() as connection:
            await login(connection, users[0], password)
            response = await connection.post("/api/v1/recruiter-chat", json={"message": MESSAGE})
            assert response.status_code == 502 and "PRIVATE_PROVIDER_DETAIL" not in response.text
            for model in (JobProfile, ChatTurn, RecruiterConversation): assert not db.get(model)
    run(scenario())


def test_unapproved_changed_or_foreign_snapshot_cannot_start_screening(workspace, monkeypatch):
    from app.api.routers import screening
    monkeypatch.setattr(screening, "BatchScreeningService", lambda **kwargs: pytest.fail("Unauthorized screening"))
    _, users, password = workspace
    async def scenario():
        async with client() as first, client() as second:
            await login(first, users[0], password)
            await login(second, users[1], password)
            job = (await first.post("/api/v1/jobs", json={"job_title": "Synthetic Engineer"})).json()
            criterion = {"criterion_id": "python", "description": "Python", "category": "skill", "is_hard": False}
            snapshot = {"job_reference": job["job_reference"], "job_title": job["job_title"], "criteria_confirmed": True, "criteria": [criterion]}
            path = f'/api/v1/cv-uploads/{job["job_reference"]}/{uuid4()}/screen'
            assert (await first.post(path, json=snapshot)).status_code == 409
            assert (await second.post(path, json=snapshot)).status_code == 404
            update = {"revision": 1, "confirmed": True, "criteria": [criterion]}
            duplicate = {**update, "criteria": [criterion, {**criterion, "criterion_id": "PYTHON"}]}
            assert (await first.put(f'/api/v1/jobs/{job["id"]}/criteria', json=duplicate)).status_code == 422
            assert (await first.put(f'/api/v1/jobs/{job["id"]}/criteria', json=update)).status_code == 200
            snapshot["criteria"][0]["is_hard"] = True
            assert (await first.post(path, json=snapshot)).status_code == 409
    run(scenario())


def test_publication_requires_owned_saved_draft_and_preserves_server_reference(workspace, monkeypatch):
    from test_recruiter_chat import MESSAGE
    from app.schemas.job_publication import PublicationResult
    _, users, password = workspace
    install_chat(monkeypatch)
    published = []
    class Publisher:
        async def publish(self, request):
            published.append(request)
            return PublicationResult(destination="discord", status="published", external_id="123456789012345678")
    monkeypatch.setattr(recruiter_chat, "get_job_publisher", Publisher)
    async def scenario():
        async with client() as first, client() as second:
            await login(first, users[0], password); await login(second, users[1], password)
            reply = (await first.post("/api/v1/recruiter-chat", json={"message": MESSAGE})).json()
            draft = reply["job_description_result"]["job_description"]
            body = {key: value for key, value in draft.items() if key != "policy_citation_ids"}
            body["job_id"] = reply["draft_id"]
            assert (await second.post("/api/v1/recruiter-chat/publish", json=body)).status_code == 404
            assert (await first.post("/api/v1/recruiter-chat/publish", json={**body, "summary": "Changed synthetic summary"})).status_code == 409
            assert not published
            response = await first.post("/api/v1/recruiter-chat/publish", json=body)
            assert response.status_code == 200
            assert set(response.json()) == {"destination", "status", "external_id"}
            assert len(published) == 1 and published[0].mcp_job()["job_reference"] == reply["job_reference"]
    run(scenario())


def test_candidate_profile_route_uses_authenticated_private_storage(workspace, monkeypatch):
    from app.api.routers import cv_uploads
    _, users, password = workspace
    captured = []
    class Profiles:
        def __init__(self, settings): captured.append(settings.cv_upload_root)
        async def parse_batch(self, *args):
            from app.services.cv_extraction import CvExtractionError
            raise CvExtractionError("batch_not_found", 404)
    async def selected(request, configuration):
        return SimpleNamespace(profiles=Profiles(configuration))
    monkeypatch.setattr(cv_uploads, "selected_screening", selected)
    async def scenario():
        async with client() as connection:
            await login(connection, users[0], password)
            job = (await connection.post("/api/v1/jobs", json={"job_title": "Synthetic Engineer"})).json()
            response = await connection.post(f'/api/v1/cv-uploads/{job["job_reference"]}/{uuid4()}/candidate-profiles')
            assert response.status_code == 404
            assert captured[0].name == str(users[0].id)
    run(scenario())


def test_migration_offline_upgrade_downgrade_and_relational_ownership():
    import io
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.upgrade(config, "0001_company_policy_knowledge:head", sql=True)
    sql = buffer.getvalue()
    for model in (Recruiter, RecruiterSession, RecruiterConversation, ChatTurn, JobProfile):
        assert f"CREATE TABLE {model.__tablename__}" in sql
    assert "JSONB" in sql and "uq_chat_sequence" in sql
    assert "CREATE EXTENSION" not in sql and "DROP TABLE" not in sql
    for model in (RecruiterSession, RecruiterConversation, JobProfile):
        foreign_keys = [c for c in model.__table__.constraints if isinstance(c, ForeignKeyConstraint)]
        assert any([e.target_fullname for e in c.elements] == ["recruiters.id"] for c in foreign_keys)
    assert any(tuple(c.columns.keys()) == ("job_reference",) for c in JobProfile.__table__.constraints if isinstance(c, UniqueConstraint))
    buffer.seek(0); buffer.truncate()
    command.downgrade(config, "head:0001_company_policy_knowledge", sql=True)
    down = buffer.getvalue()
    assert "DROP TABLE job_profiles" in down and "DROP TABLE recruiter_sessions" in down
    assert "DROP TABLE knowledge" not in down and "DROP EXTENSION" not in down


def test_blocked_logins_do_not_extend_rate_limit_and_expose_bounded_retry_after(monkeypatch):
    from starlette.requests import Request
    from starlette.responses import Response
    clock=[100.0]
    monkeypatch.setattr(auth, "time", SimpleNamespace(monotonic=lambda:clock[0]))
    request=Request({"type":"http","method":"POST","path":"/login","headers":[],"client":("synthetic-local",1)})
    key=token_hash("synthetic-local")
    body=auth.LoginRequest(email="synthetic@example.test",password="synthetic-test-only")
    class DatabaseBoundary:
        async def scalar(self,query):raise LookupError("Database boundary reached")
    async def scenario():
        auth._attempts.clear();auth._attempts[key]=[0.,1.,2.,3.,4.]
        try:
            for now,remaining in [(100.,200),(299.,1)]:
                clock[0]=now
                with pytest.raises(HTTPException) as error:
                    await auth.login(body,request,Response(),DatabaseBoundary())
                assert error.value.status_code==429
                assert error.value.headers["Retry-After"]==str(remaining)
                assert auth._attempts[key]==[0.,1.,2.,3.,4.]
            clock[0]=301.
            with pytest.raises(LookupError):
                await auth.login(body,request,Response(),DatabaseBoundary())
            assert auth._attempts[key]==[2.,3.,4.,301.]
        finally:auth._attempts.clear()
    asyncio.run(scenario())
