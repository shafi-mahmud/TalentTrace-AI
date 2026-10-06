import asyncio

import httpx

from app.main import app


async def get_health_response() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get("/api/v1/health")


def test_health_check() -> None:
    response = asyncio.run(get_health_response())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "talenttrace-api",
    }
