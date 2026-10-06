"""Anomaly detection: flag runs and LLM calls that are far outside their own normal.

Baselines are per agent and per model (a self-hosted 14B model and a hosted API have different
normals). An outlier must clear BOTH a relative bar (N x the median) and a robust statistical bar
(median + k x MAD), so a noisy-but-normal run never pages anyone. Median/MAD are used instead of
mean/stddev because the outliers we are hunting would drag a mean up and hide themselves.
"""
import statistics

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from server.models import Alert, Run, Span

MIN_HISTORY = 20       # don't judge until we know what normal looks like
K_MAD = 8.0            # robust z-score bar
RUN_RATIO = 5.0        # run cost/duration must also be >= 5x the median
CALL_RATIO = 10.0      # an LLM call must produce >= 10x the median output tokens
CALL_MIN_TOKENS = 1000
CRITICAL_RATIO = 20.0
MIN_EXTRA_COST = 0.01      # ...and be at least this much above normal in absolute terms,
MIN_EXTRA_MS = 30_000      # so a 2 s run against a 0.1 s median never pages anyone


def outlier(value, history, ratio, min_extra=0.0):
    """Return (median, value/median) if value is an outlier versus history, else None."""
    if value is None or len(history) < MIN_HISTORY:
        return None
    med = statistics.median(history)
    if med <= 0:
        return None
    mad = statistics.median(abs(v - med) for v in history) * 1.4826
    if value > max(med * ratio, med + K_MAD * mad, med + min_extra):
        return med, value / med
    return None


async def _alert(session, run, kind, message, value, baseline, ratio, span_id=None):
    await session.execute(insert(Alert).values(
        dedup_key=f"{kind}:{run.id}:{span_id or '-'}", agent_name=run.agent_name, model=run.model,
        run_id=run.id, span_id=span_id, kind=kind, severity="critical" if ratio >= CRITICAL_RATIO else "warning",
        message=message, value=value, baseline=baseline).on_conflict_do_nothing(index_elements=["dedup_key"]))


def _usd(v):
    return f"${v:.5f}" if v < 0.001 else f"${v:.4f}" if v < 0.01 else f"${v:.3f}"


async def check_run(session, run_id):
    run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if run is None or run.status == "running":
        return
    peers = (await session.execute(select(Run.cost_usd, Run.latency_ms).where(
        Run.agent_name == run.agent_name, Run.model == run.model, Run.status != "running", Run.id != run.id)
        .order_by(Run.started_at.desc()).limit(300))).all()
    costs = [c for c, _ in peers if c]
    lats = [lat for _, lat in peers if lat]
    model = run.model or "this agent"

    hit = outlier(run.cost_usd, costs, RUN_RATIO, MIN_EXTRA_COST)
    if hit:
        med, ratio = hit
        await _alert(session, run, "cost_spike",
                     f"Run cost {_usd(run.cost_usd)}, {ratio:,.0f}x the median {_usd(med)} for {model}.",
                     run.cost_usd, med, ratio)
    hit = outlier(run.latency_ms, lats, RUN_RATIO, MIN_EXTRA_MS)
    if hit:
        med, ratio = hit
        await _alert(session, run, "latency_spike",
                     f"Run took {run.latency_ms / 1000:.1f} s, {ratio:,.0f}x the median {med / 1000:.1f} s for {model}.",
                     run.latency_ms, med, ratio)

    # Runaway generation: one LLM call producing far more output than this model normally does.
    calls = (await session.execute(select(Span.id, Span.model, Span.completion_tokens, Span.latency_ms).where(
        Span.run_id == run.id, Span.kind == "llm"))).all()
    for call in calls:
        normal = (await session.execute(select(Span.completion_tokens, Span.latency_ms).where(
            Span.kind == "llm", Span.model == call.model, Span.run_id != run.id)
            .order_by(Span.started_at.desc()).limit(2000))).all()
        if call.completion_tokens:
            hit = outlier(call.completion_tokens, [t for t, _ in normal if t], CALL_RATIO)
            if hit and call.completion_tokens >= CALL_MIN_TOKENS:
                med, ratio = hit
                await _alert(session, run, "runaway_generation",
                             f"One LLM call generated {call.completion_tokens:,} tokens, {ratio:,.0f}x the median "
                             f"{med:.0f} for {call.model}. Cap max output tokens.",
                             call.completion_tokens, med, ratio, span_id=call.id)
        elif call.latency_ms:  # no token count reported: fall back to call duration
            hit = outlier(call.latency_ms, [lat for _, lat in normal if lat], CALL_RATIO, MIN_EXTRA_MS)
            if hit:
                med, ratio = hit
                await _alert(session, run, "runaway_generation",
                             f"One LLM call ran {call.latency_ms / 1000:.0f} s, {ratio:,.0f}x the median "
                             f"{med / 1000:.1f} s for {call.model}.", call.latency_ms, med, ratio, span_id=call.id)

    if run.error_type == "BudgetExceeded":
        await _alert(session, run, "budget_exceeded",
                     f"Guardrail stopped the run: {run.failure_reason or 'budget exceeded'}", None, None, CRITICAL_RATIO)


async def scan(session, agent=None):
    """Re-check every finished run (e.g. after upgrading, or to backfill history)."""
    q = select(Run.id).where(Run.status != "running").order_by(Run.started_at)
    if agent:
        q = q.where(Run.agent_name == agent)
    ids = (await session.execute(q)).scalars().all()
    for rid in ids:
        await check_run(session, rid)
    await session.commit()
    return len(ids)
