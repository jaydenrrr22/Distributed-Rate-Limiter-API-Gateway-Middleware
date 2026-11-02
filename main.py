import os
from fastapi import FastAPI
import redis.asyncio as redis

app = FastAPI(title="Distrubuted Rate Limiter Gateway")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6349))

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

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