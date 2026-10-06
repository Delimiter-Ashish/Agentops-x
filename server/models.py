"""Data model.

  prompt_versions 1──* runs 1──* spans (self-referencing tree via parent_id)

Runs carry denormalized aggregates (tokens, cost, retries, peak memory...) computed server-side
from their spans when the run ends, so dashboards never have to scan the spans table.
"""
import datetime as dt
import uuid

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("agent_name", "template_hash", name="uq_prompt_agent_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(200))
    template: Mapped[str] = mapped_column(Text)
    template_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_agent_started", "agent_name", "started_at"),
        Index("ix_runs_prompt_status", "prompt_version_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(200))
    prompt_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_versions.id"))
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)  # running|success|failure|error
    task_success: Mapped[bool | None] = mapped_column(Boolean)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(200))
    input: Mapped[dict | None] = mapped_column(JSONType)
    output: Mapped[dict | None] = mapped_column(JSONType)
    tags: Mapped[list | None] = mapped_column(JSONType)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONType)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # aggregates, filled in when the run ends
    latency_ms: Mapped[float | None] = mapped_column(Float)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_errors: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    peak_memory_mb: Mapped[float | None] = mapped_column(Float)
    max_state_bytes: Mapped[int | None] = mapped_column(Integer)

    prompt_version: Mapped[PromptVersion | None] = relationship(lazy="joined")


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (
        Index("ix_spans_run_started", "run_id", "started_at"),
        Index("ix_spans_kind_name", "kind", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(16))        # graph|node|llm|tool
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16))      # ok|error
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    ttft_ms: Mapped[float | None] = mapped_column(Float)
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    memory_mb: Mapped[float | None] = mapped_column(Float)
    state_size_bytes: Mapped[int | None] = mapped_column(Integer)
    input: Mapped[dict | list | str | None] = mapped_column(JSONType)
    output: Mapped[dict | list | str | None] = mapped_column(JSONType)
    error: Mapped[dict | None] = mapped_column(JSONType)
    attributes: Mapped[dict | None] = mapped_column(JSONType)
