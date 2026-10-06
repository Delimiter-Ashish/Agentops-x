"""Ingestion pipeline.

Every write is an idempotent upsert keyed by client-generated UUIDs, so the SDK can safely
retry a batch. Run aggregates are recomputed from spans inside the same transaction as run_end.
"""
import hashlib

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from server.models import PromptVersion, Run, Span
from server.schemas import RunEnd, RunStart, SpanIn


async def _prompt_version_id(session, agent, pv):
    digest = hashlib.sha256(pv.template.encode()).hexdigest()
    await session.execute(
        insert(PromptVersion)
        .values(agent_name=agent, name=pv.name, template=pv.template, template_hash=digest)
        .on_conflict_do_nothing(constraint="uq_prompt_agent_hash"))
    return (await session.execute(select(PromptVersion.id).where(
        PromptVersion.agent_name == agent, PromptVersion.template_hash == digest))).scalar_one()


async def _run_start(session, ev: RunStart):
    pv_id = await _prompt_version_id(session, ev.agent, ev.prompt_version) if ev.prompt_version else None
    values = dict(id=ev.id, agent_name=ev.agent, prompt_version_id=pv_id, input=ev.input, tags=ev.tags,
                  meta=ev.metadata, started_at=ev.started_at, status="running")
    stmt = insert(Run).values(**values)
    await session.execute(stmt.on_conflict_do_update(
        index_elements=[Run.id],
        set_={k: stmt.excluded[k] for k in ("agent_name", "prompt_version_id", "input", "tags",
                                             "started_at")} | {"metadata": stmt.excluded["metadata"]}))


async def _span(session, ev: SpanIn):
    # Spans can outrun their run_start (e.g. a retried batch); create a placeholder run if needed.
    await session.execute(insert(Run).values(id=ev.run_id, agent_name="unknown", started_at=ev.started_at,
                                             status="running").on_conflict_do_nothing(index_elements=[Run.id]))
    values = ev.model_dump(exclude={"type"})
    stmt = insert(Span).values(**values)
    await session.execute(stmt.on_conflict_do_update(
        index_elements=[Span.id], set_={k: stmt.excluded[k] for k in values if k != "id"}))


async def _run_end(session, ev: RunEnd):
    agg = (await session.execute(select(
        func.count().filter(Span.kind == "llm"),
        func.count().filter(Span.kind == "tool"),
        func.count().filter((Span.kind == "tool") & (Span.status == "error")),
        func.count().filter((Span.kind == "node") & (Span.attempt > 1)),
        func.coalesce(func.sum(Span.prompt_tokens), 0),
        func.coalesce(func.sum(Span.completion_tokens), 0),
        func.coalesce(func.sum(Span.cost_usd), 0.0),
        func.max(Span.memory_mb),
        func.max(Span.state_size_bytes),
        func.min(Span.started_at),
    ).where(Span.run_id == ev.id))).one()
    run_started = (await session.execute(select(Run.started_at).where(Run.id == ev.id))).scalar_one_or_none()
    start = run_started or agg[9]
    latency = (ev.ended_at - start).total_seconds() * 1000 if start else None
    await session.execute(update(Run).where(Run.id == ev.id).values(
        status=ev.status, ended_at=ev.ended_at, output=ev.output, task_success=ev.task_success,
        failure_reason=ev.failure_reason, error_type=ev.error_type, latency_ms=latency,
        llm_calls=agg[0], tool_calls=agg[1], tool_errors=agg[2], retries=agg[3],
        prompt_tokens=agg[4], completion_tokens=agg[5], cost_usd=agg[6],
        peak_memory_mb=agg[7], max_state_bytes=agg[8]))


HANDLERS = {"run_start": _run_start, "span": _span, "run_end": _run_end}


async def ingest(session, events):
    # Order matters: run_start before spans before run_end. A batch is applied in order, atomically.
    for ev in events:
        await HANDLERS[ev.type](session, ev)
    await session.commit()
    return len(events)

