"""Query API used by the dashboard and CLI."""
import datetime as dt
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal_column, select

from server.db import get_session
from server.models import GpuSample, PromptVersion, Run, Span

router = APIRouter(prefix="/api")

RUN_FIELDS = ("id", "agent_name", "model", "status", "task_success", "failure_reason", "error_type", "started_at",
              "ended_at", "latency_ms", "llm_calls", "tool_calls", "tool_errors", "retries", "prompt_tokens",
              "completion_tokens", "cost_usd", "peak_memory_mb", "max_state_bytes", "tags")
SPAN_FIELDS = ("id", "parent_id", "kind", "name", "status", "attempt", "started_at", "ended_at", "latency_ms",
               "ttft_ms", "model", "prompt_tokens", "completion_tokens", "cost_usd", "memory_mb",
               "state_size_bytes", "input", "output", "error", "attributes")


def run_dict(r, detail=False):
    d = {f: getattr(r, f) for f in RUN_FIELDS}
    d["prompt_version"] = r.prompt_version.name if r.prompt_version else None
    if detail:
        d.update(input=r.input, output=r.output, metadata=r.meta,
                 prompt_template=r.prompt_version.template if r.prompt_version else None)
    return d


def tokens_per_s(span):
    """Decode speed: output tokens / time spent generating (after the first token, when streamed)."""
    toks, lat = span.get("completion_tokens"), span.get("latency_ms")
    if not toks or not lat:
        return None
    gen_ms = lat - (span.get("ttft_ms") or 0)
    return toks / (gen_ms / 1000) if gen_ms > 0 else None


def gpu_context(span, samples):
    """GPU / inference-server state while this LLM call was running."""
    if not span.get("ended_at"):
        return None
    pad = dt.timedelta(seconds=1)
    win = [g for g in samples if span["started_at"] - pad <= g.ts <= span["ended_at"] + pad]
    if not win:
        return None
    avg = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    vals = lambda f: [getattr(g, f) for g in win if getattr(g, f) is not None]  # noqa: E731
    return {"samples": len(win), "util_pct": avg(vals("util_pct")), "kv_cache_pct": avg(vals("kv_cache_pct")),
            "requests_running": avg(vals("requests_running")), "requests_waiting": avg(vals("requests_waiting")),
            "mem_used_mb": max(vals("mem_used_mb"), default=None), "power_w": avg(vals("power_w"))}


def wilson(successes, n, z=1.96):
    """95% Wilson score interval: honest error bars for a success rate, even with few runs."""
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def two_proportion_p(s1, n1, s2, n2):
    """Two-sided p-value: is the success-rate difference between two prompt versions real?"""
    if min(n1, n2) == 0:
        return None
    pooled = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(s1 / n1 - s2 / n2) / se
    return math.erfc(z / math.sqrt(2))


@router.get("/agents")
async def agents(session=Depends(get_session)):
    rows = (await session.execute(select(
        Run.agent_name, func.count(), func.max(Run.started_at),
        func.avg(case((Run.status == "success", 1.0), else_=0.0))).group_by(Run.agent_name))).all()
    return [{"agent": a, "runs": n, "last_run": last, "success_rate": sr} for a, n, last, sr in rows]


@router.get("/runs")
async def list_runs(agent: str | None = None, status: str | None = None, prompt_version: str | None = None,
                    limit: int = Query(50, le=500), offset: int = 0, session=Depends(get_session)):
    q = select(Run).order_by(Run.started_at.desc()).limit(limit).offset(offset)
    if agent:
        q = q.where(Run.agent_name == agent)
    if status:
        q = q.where(Run.status == status)
    if prompt_version:
        q = q.join(PromptVersion).where(PromptVersion.name == prompt_version)
    return [run_dict(r) for r in (await session.execute(q)).scalars().all()]


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, session=Depends(get_session)):
    run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "run not found")
    spans = [{f: getattr(s, f) for f in SPAN_FIELDS} for s in (await session.execute(
        select(Span).where(Span.run_id == run_id).order_by(Span.started_at))).scalars().all()]
    samples = []
    if spans and run.ended_at:
        pad = dt.timedelta(seconds=2)
        samples = (await session.execute(select(GpuSample).where(
            GpuSample.ts >= run.started_at - pad, GpuSample.ts <= run.ended_at + pad))).scalars().all()
    for sp in spans:
        if sp["kind"] == "llm":
            sp["tokens_per_s"] = tokens_per_s(sp)
            sp["gpu"] = gpu_context(sp, samples) if samples else None
    return {"run": run_dict(run, detail=True), "spans": spans}


@router.get("/prompt-versions")
async def prompt_versions(agent: str, model: str | None = None, session=Depends(get_session)):
    """Side-by-side reliability, latency and cost per prompt version, with confidence intervals."""
    done = Run.status != "running"
    rows = (await session.execute(select(
        PromptVersion.name, PromptVersion.id, PromptVersion.created_at,
        func.count(Run.id).filter(done),
        func.count(Run.id).filter(Run.status == "success"),
        func.count(Run.id).filter(Run.status == "error"),
        func.percentile_cont(0.5).within_group(Run.latency_ms).filter(done),
        func.percentile_cont(0.95).within_group(Run.latency_ms).filter(done),
        func.avg(Run.cost_usd).filter(done),
        func.avg(Run.prompt_tokens + Run.completion_tokens).filter(done),
        func.avg(Run.retries).filter(done),
        func.avg(Run.tool_errors).filter(done),
    ).join(Run, Run.prompt_version_id == PromptVersion.id)
        .where(PromptVersion.agent_name == agent, *([Run.model == model] if model else []))
        .group_by(PromptVersion.id).order_by(PromptVersion.created_at))).all()
    out = []
    for name, pv_id, created, n, ok, err, p50, p95, cost, tokens, retries, tool_err in rows:
        lo, hi = wilson(ok, n)
        out.append({"prompt_version": name, "id": pv_id, "created_at": created, "runs": n, "successes": ok,
                    "errors": err, "success_rate": ok / n if n else None, "success_ci95": [lo, hi],
                    "p50_latency_ms": p50, "p95_latency_ms": p95, "avg_cost_usd": cost,
                    "avg_tokens": tokens, "avg_retries": retries, "avg_tool_errors": tool_err})
    if len(out) >= 2:
        best = max(out, key=lambda r: r["success_rate"] or 0)
        for r in out:
            r["p_value_vs_best"] = None if r is best else two_proportion_p(
                r["successes"], r["runs"], best["successes"], best["runs"])
    return out


@router.get("/failures")
async def failures(agent: str, limit: int = 20, session=Depends(get_session)):
    """Failure breakdown: where runs break (error type / reason) and which tools fail most."""
    by_reason = (await session.execute(select(
        Run.status, func.coalesce(Run.error_type, "wrong_answer"), func.count(),
        func.min(Run.failure_reason)).where(
        Run.agent_name == agent, Run.status.in_(["failure", "error"])).group_by(
        Run.status, Run.error_type).order_by(func.count().desc()).limit(limit))).all()
    by_tool = (await session.execute(select(
        Span.name, func.count(), func.count().filter(Span.status == "error"),
        func.percentile_cont(0.95).within_group(Span.latency_ms)).join(Run, Run.id == Span.run_id).where(
        Run.agent_name == agent, Span.kind == "tool").group_by(Span.name).order_by(Span.name))).all()
    return {
        "by_reason": [{"status": s, "type": t, "count": c, "example": ex} for s, t, c, ex in by_reason],
        "by_tool": [{"tool": n, "calls": c, "errors": e, "error_rate": e / c if c else None, "p95_latency_ms": p}
                    for n, c, e, p in by_tool],
    }


@router.get("/timeseries")
async def timeseries(agent: str, bucket: str = Query("minute", pattern="^(minute|hour|day)$"),
                     session=Depends(get_session)):
    t = func.date_trunc(literal_column(f"'{bucket}'"), Run.started_at).label("t")  # bucket is regex-validated
    rows = (await session.execute(select(
        t, func.count(), func.avg(case((Run.status == "success", 1.0), else_=0.0)),
        func.percentile_cont(0.95).within_group(Run.latency_ms), func.sum(Run.cost_usd)).where(
        Run.agent_name == agent, Run.status != "running").group_by(t).order_by(t))).all()
    return [{"t": ts, "runs": n, "success_rate": sr, "p95_latency_ms": p95, "cost_usd": c}
            for ts, n, sr, p95, c in rows]


@router.get("/models")
async def models(agent: str, session=Depends(get_session)):
    """Head-to-head comparison of the LLMs an agent ran on (e.g. a hosted API vs a self-hosted model)."""
    done = Run.status != "running"
    rows = (await session.execute(select(
        Run.model, func.count(Run.id), func.count(Run.id).filter(Run.status == "success"),
        func.percentile_cont(0.5).within_group(Run.latency_ms),
        func.percentile_cont(0.95).within_group(Run.latency_ms),
        func.avg(Run.cost_usd), func.avg(Run.prompt_tokens + Run.completion_tokens), func.avg(Run.retries),
    ).where(Run.agent_name == agent, done, Run.model.is_not(None)).group_by(Run.model))).all()
    speed = {m: (ttft, ctoks, gen_ms) for m, ttft, ctoks, gen_ms in (await session.execute(select(
        Span.model, func.percentile_cont(0.5).within_group(Span.ttft_ms),
        func.sum(Span.completion_tokens), func.sum(Span.latency_ms - func.coalesce(Span.ttft_ms, 0.0)),
    ).join(Run, Run.id == Span.run_id).where(Run.agent_name == agent, Span.kind == "llm",
                                             Span.status == "ok").group_by(Span.model))).all()}
    out = []
    for m, n, ok, p50, p95, cost, toks, retries in rows:
        lo, hi = wilson(ok, n)
        ttft, ctoks, gen_ms = speed.get(m, (None, None, None))
        out.append({"model": m, "runs": n, "success_rate": ok / n if n else None, "success_ci95": [lo, hi],
                    "p50_latency_ms": p50, "p95_latency_ms": p95, "avg_cost_usd": cost, "avg_tokens": toks,
                    "avg_retries": retries, "p50_ttft_ms": ttft,
                    "tokens_per_s": (ctoks / (gen_ms / 1000)) if ctoks and gen_ms else None})
    return out


@router.get("/gpu/timeseries")
async def gpu_timeseries(minutes: int = Query(30, le=24 * 60), session=Depends(get_session)):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)
    rows = (await session.execute(select(GpuSample).where(GpuSample.ts >= since).order_by(GpuSample.ts))).scalars().all()
    fields = ("ts", "gpu_index", "gpu_name", "util_pct", "mem_used_mb", "mem_total_mb", "power_w", "temp_c",
              "kv_cache_pct", "requests_running", "requests_waiting", "gen_tokens_per_s", "prompt_tokens_per_s")
    return [{f: getattr(r, f) for f in fields} for r in rows]
