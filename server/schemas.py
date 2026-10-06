"""Ingestion contract. Events are a discriminated union on `type`."""
import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class PromptVersionIn(BaseModel):
    name: str = Field(max_length=200)
    template: str


class RunStart(BaseModel):
    type: Literal["run_start"]
    id: uuid.UUID
    agent: str = Field(max_length=200)
    started_at: dt.datetime
    input: Any = None
    prompt_version: PromptVersionIn | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class SpanIn(BaseModel):
    type: Literal["span"]
    id: uuid.UUID
    run_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    kind: Literal["graph", "node", "llm", "tool"]
    name: str = Field(max_length=300)
    status: Literal["ok", "error"]
    attempt: int = 1
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    latency_ms: float | None = None
    ttft_ms: float | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    memory_mb: float | None = None
    state_size_bytes: int | None = None
    input: Any = None
    output: Any = None
    error: dict[str, Any] | None = None
    attributes: dict[str, Any] = {}


class RunEnd(BaseModel):
    type: Literal["run_end"]
    id: uuid.UUID
    status: Literal["success", "failure", "error"]
    ended_at: dt.datetime
    output: Any = None
    task_success: bool | None = None
    failure_reason: str | None = None
    error_type: str | None = None


Event = Annotated[RunStart | SpanIn | RunEnd, Field(discriminator="type")]


class IngestBatch(BaseModel):
    events: list[Event] = Field(max_length=5000)


class GpuSampleIn(BaseModel):
    ts: dt.datetime
    host: str | None = None
    gpu_index: int | None = None
    gpu_name: str | None = None
    util_pct: float | None = None
    mem_used_mb: float | None = None
    mem_total_mb: float | None = None
    power_w: float | None = None
    temp_c: float | None = None
    kv_cache_pct: float | None = None
    requests_running: float | None = None
    requests_waiting: float | None = None
    gen_tokens_per_s: float | None = None
    prompt_tokens_per_s: float | None = None


class GpuBatch(BaseModel):
    samples: list[GpuSampleIn] = Field(max_length=5000)
