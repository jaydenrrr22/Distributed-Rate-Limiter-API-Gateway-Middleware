import os
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis

app = FastAPI(title="Distrubuted Rate Limiter Gateway")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
lua_script_sha = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global lua_script_sha
    with open("sliding_window.lua", "r") as f:
        script_content = f.read()
    lua_script_sha = await redis_client.script_load(script_content)
    yield
    await redis_client.close()

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    api_key = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization")

    if api_key:
        key = f"rate_limit:apikey:{api_key}"
        window_seconds = 60
        max_requests = 100
    elif auth_header:
        key = f"rate_limit:apikey:{auth_header}"
        window_seconds = 60
        max_requests = 30
    else:
        client_ip = request.client.host if request.client else "Unknown"
        key = f"rate_limit:ip:{client_ip}"
        window_seconds = 60
        max_requests = 5
    
    now = time.time()
    now_ms = int(now * 1000)
    request_id = f"{now_ms}:{uuid.uuid4().hex}"

    try:
        res = await redis_client.evalsha(
            lua_script_sha, 
            1, 
            key, 
            str(now_ms), 
            str(window_seconds), 
            str(max_requests),
            request_id
        )
        is_allowed, remaining = res[0], res[1]
    except Exception as e:
        print(f"REDIS ERROR: {e}")
        return await call_next(request)
    
    if is_allowed == 0:
        return JSONResponse(
            status_code = status.HTTP_429_TOO_MANY_REQUESTS,
            content={"details": "Rate limit exceeded. Try again later."},
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(window_seconds),
            },
        )
    
    response: Response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response

@app.get("/api/data")
async def get_data():
    return {"data": "Success! You are within your rate limit"}

@app.get("/")
async def root():
    return {"message": "FastAPI & Radis orchestration is running"}

@app.get("/health")
async def health_check():
    try:
        pong = await redis_client.ping()
        if pong:
            return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "redis_error": str(e)}