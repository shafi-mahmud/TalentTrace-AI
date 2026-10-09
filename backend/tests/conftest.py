"""Legacy business-contract API tests run with an explicitly mocked owned workspace.

Authentication/ownership is exercised WITHOUT these overrides in test_recruiter_records.py.
Domain tests retain their original provider mocks and never make live LLM calls.
"""
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import AsyncMock
import sys

import pytest


@pytest.fixture(autouse=True)
def authenticated_business_contracts(request, monkeypatch):
    legacy = {"test_batch_screening", "test_cv_uploads", "test_cv_extraction", "test_cv_ocr",
        "test_candidate_profile", "test_job_descriptions_endpoint", "test_recruiter_chat",
        "test_job_publication", "test_semantic_jd_factory", "test_groq_job_description", "test_screening_ranking"}
    if request.node.path.stem not in legacy:
        yield
        return
    from app.main import app
    from app.core.auth import current_recruiter, database_session
    from app.api.routers import recruiter_chat, cv_uploads, screening
    from app.core.config import settings

    async def user():
        return SimpleNamespace(id=UUID("00000000-0000-4000-8000-000000000001"))

    async def database():
        yield AsyncMock()

    async def owned(*args, **kwargs):
        return None

    async def conversation(session, owner_id, body, service, correlation_id):
        return await service.respond(body, correlation_id=correlation_id)

    # A foundation test reloads app.main; previously imported API clients still use
    # their original app. Explicitly authenticate those test apps as well.
    apps = {app}
    for name, module in list(sys.modules.items()):
        if name.startswith("test_") and hasattr(module, "app"):
            apps.add(module.app)
    previous = {target: dict(target.dependency_overrides) for target in apps}
    for target in apps:
        target.dependency_overrides[current_recruiter] = user
        target.dependency_overrides[database_session] = database
    monkeypatch.setattr(recruiter_chat, "persist_chat", conversation)
    monkeypatch.setattr(recruiter_chat, "authorize_publication", owned)
    monkeypatch.setattr(cv_uploads, "owned_reference", owned)
    # Each existing CV test sets its own root/configuration on its route module.
    monkeypatch.setattr(cv_uploads, "private_settings", lambda request: cv_uploads.settings)
    monkeypatch.setattr(screening, "authorize_snapshot", owned)
    monkeypatch.setattr(screening, "private_settings", lambda request: settings)
    yield
    for target in apps:
        target.dependency_overrides.clear()
        target.dependency_overrides.update(previous[target])
