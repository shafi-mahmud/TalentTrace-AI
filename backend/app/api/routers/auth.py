"""Administrator-provisioned login; no public registration or password disclosure."""
import secrets
import time
import math
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, field_validator
from sqlalchemy import delete, select
from starlette.concurrency import run_in_threadpool

from app.core.auth import COOKIE_NAME, current_recruiter, database_session, dummy_password_hash, protect_mutation, token_hash, verify_password
from app.core.config import settings
from app.db.models.recruiter import Recruiter, RecruiterSession

router = APIRouter(prefix="/auth", tags=["Recruiter authentication"])
# Bounds online guessing before costly password work. Deployment-wide limiting remains required.
_attempts: OrderedDict[str, list[float]] = OrderedDict()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
    password: SecretStr

    @field_validator("password", mode="before")
    @classmethod
    def password_length(cls, value):
        if not isinstance(value, str) or not 1 <= len(value) <= 128:
            raise ValueError("Invalid password length.")
        return value

    def bounded_password(self):
        value = self.password.get_secret_value()
        if not 1 <= len(value) <= 128:
            raise HTTPException(401, "Invalid sign-in details.")
        return value


@router.post("/login", dependencies=[Depends(protect_mutation)])
async def login(body: LoginRequest, request: Request, response: Response, session=Depends(database_session)):
    password = body.bounded_password()
    key = token_hash(request.client.host if request.client else "unknown")
    now = time.monotonic()
    recent = [stamp for stamp in _attempts.pop(key, []) if now - stamp < 300]
    if len(_attempts) >= 1000:
        _attempts.popitem(last=False)
    if len(recent) >= 5:
        # Rejected requests must not renew the lockout window.
        _attempts[key] = recent
        retry_after = max(1, math.ceil(300 - (now - recent[0])))
        raise HTTPException(429, "Too many sign-in attempts. Wait before trying again.",
                            headers={"Retry-After": str(retry_after)})
    _attempts[key] = recent + [now]
    user = await session.scalar(select(Recruiter).where(Recruiter.email == body.email.casefold()))
    # Equal-cost password work even for unknown accounts; no account enumeration response.
    encoded = user.password_hash if user else await run_in_threadpool(dummy_password_hash)
    valid = await run_in_threadpool(verify_password, password, encoded)
    if not user or not user.active or not valid:
        raise HTTPException(401, "Invalid sign-in details.")
    token = secrets.token_urlsafe(32)
    session.add(RecruiterSession(token_hash=token_hash(token), recruiter_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8)))
    await session.commit()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=settings.environment != "development",
        samesite="strict", max_age=8*3600, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"id": str(user.id), "email": user.email}


@router.get("/me")
async def me(user=Depends(current_recruiter)):
    return {"id": str(user.id), "email": user.email}


@router.post("/logout")
async def logout(request: Request, response: Response, user=Depends(current_recruiter), session=Depends(database_session)):
    await session.execute(delete(RecruiterSession).where(RecruiterSession.token_hash == token_hash(request.cookies[COOKIE_NAME])))
    await session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "signed_out"}
