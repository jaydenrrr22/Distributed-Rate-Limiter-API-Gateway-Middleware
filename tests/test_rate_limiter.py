import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from main import app, redis_client

@pytest.fixture(autouse=True)
async def clear_redis():
    """Flush test keys before each test for clean state."""
    await redis_client.flushdb()
    yield
    await redis_client.flushdb()

@pytest.mark.asyncio
async def test_anonymous_ip_rate_limit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First 5 requests should succeed
        for i in range(5):
            res = await client.get("/api/data")
            assert res.status_code == 200
            assert res.headers["X-RateLimit-Limit"] == "5"
            assert res.headers["X-RateLimit-Remaining"] == str(4 - i)

        # 6th request should be blocked
        blocked = await client.get("/api/data")
        assert blocked.status_code == 429
        assert blocked.headers["X-RateLimit-Remaining"] == "0"
        assert "Retry-After" in blocked.headers

@pytest.mark.asyncio
async def test_tier_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Exhaust anonymous IP tier
        for _ in range(5):
            await client.get("/api/data")
        assert (await client.get("/api/data")).status_code == 429

        # Auth tier (30/min) should still succeed independently
        auth_res = await client.get(
            "/api/data", headers={"Authorization": "Bearer test_token"}
        )
        assert auth_res.status_code == 200
        assert auth_res.headers["X-RateLimit-Limit"] == "30"
        assert auth_res.headers["X-RateLimit-Remaining"] == "29"

        # API Key tier (100/min) should also succeed independently
        key_res = await client.get(
            "/api/data", headers={"X-API-Key": "test_api_key"}
        )
        assert key_res.status_code == 200
        assert key_res.headers["X-RateLimit-Limit"] == "100"
        assert key_res.headers["X-RateLimit-Remaining"] == "99"

@pytest.mark.asyncio
async def test_concurrency_atomicity():
    """Fire 20 simultaneous requests to verify Lua script prevents race conditions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tasks = [client.get("/api/data") for _ in range(20)]
        responses = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in responses]
        assert status_codes.count(200) == 5
        assert status_codes.count(429) == 15