"""AgentOps-X collector + query API.

    uvicorn server.main:app --host 127.0.0.1 --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from server import api
from server.config import settings
from server.db import engine, get_session
from server.ingest import ingest, ingest_gpu
from server.models import Base
from server.schemas import GpuBatch, IngestBatch

# Additive schema changes for databases created by an earlier version (proper migrations: Phase 5).
UPGRADES = [
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS model VARCHAR(200)",
    "CREATE INDEX IF NOT EXISTS ix_runs_model ON runs (model)",
]


@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in UPGRADES:
            await conn.execute(text(stmt))
    yield
    await engine.dispose()


app = FastAPI(title="AgentOps-X", version="0.1.0", lifespan=lifespan, root_path=settings.root_path)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api.router)


def check_key(x_agentops_key: str | None = Header(default=None)):
    if settings.api_key and x_agentops_key != settings.api_key:
        raise HTTPException(401, "invalid or missing X-AgentOps-Key")


@app.post("/v1/ingest", status_code=202, dependencies=[Depends(check_key)])
async def ingest_events(batch: IngestBatch, session=Depends(get_session)):
    return {"accepted": await ingest(session, batch.events)}


@app.post("/v1/gpu", status_code=202, dependencies=[Depends(check_key)])
async def ingest_gpu_samples(batch: GpuBatch, session=Depends(get_session)):
    return {"accepted": await ingest_gpu(session, batch.samples)}


@app.get("/healthz")
async def healthz():
    return {"ok": True}
