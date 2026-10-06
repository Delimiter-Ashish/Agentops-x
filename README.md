# AgentOps-X 🔭

**Observability and reliability engineering for production LangGraph agents.**

An agent can look great in a demo and still fail quietly across real executions. When it does, was it a tool call, a prompt change, a retry storm, latency, cost, or the agent's state? AgentOps-X makes every execution traceable so you can answer that with data.

> Status: **Phase 1, core platform.** SDK, collector, PostgreSQL data model, query API, and a demo agent with fault injection.

## What it captures
For every run of a LangGraph agent, with one line of instrumentation:

| Signal | How |
|---|---|
| **Trace tree** | graph → nodes → LLM calls / tool calls, as parent-child spans |
| **Retries** | re-executions of a node in the same graph step (LangGraph `RetryPolicy`) plus LLM-client retries |
| **Tool failures** | hard errors (exceptions) and soft errors (tools that return `ERROR...`) |
| **Latency** | per span and per run, p50/p95 per prompt version |
| **Cost** | tokens and USD per LLM call (configurable price table) |
| **Memory** | process RSS per span, peak per run, and agent state size |
| **Task success** | `run.mark_success(...)` with your own checker, separate from crashes |

```python
import agentops

agentops.init()   # AGENTOPS_ENDPOINT, AGENTOPS_API_KEY from env
with agentops.run("fin-agent", input={"question": q}, prompt_version=("v2", PROMPT)) as run:
    result = graph.invoke(state, config={"callbacks": [run.callback]})
    run.mark_success(is_correct(result))
```

The SDK never breaks or blocks the agent: events go through a bounded queue to a background exporter that batches, retries, and drops (with a counter) if the collector is down.

## Architecture

```
  LangGraph agent ──callbacks──► SDK (batching exporter) ──HTTP──► FastAPI collector ──► PostgreSQL
                                                                         │
                                         query API: runs · traces · prompt versions · failures · timeseries
```

**Data model:** `prompt_versions 1─* runs 1─* spans` (spans form a tree via `parent_id`). Prompt versions are content-addressed (SHA-256 of the template), so editing a prompt automatically creates a new version. Every ingest is an idempotent upsert on client-generated UUIDs, so retried batches never duplicate data. Run aggregates (tokens, cost, retries, tool errors, peak memory) are computed server-side from spans in the same transaction as `run_end`.

## Prompt version comparison with statistics
`GET /api/prompt-versions?agent=fin-agent` returns success rate with a **95% Wilson confidence interval**, p50/p95 latency, cost per run, retries, and tool errors for each version, plus a **two-proportion z-test p-value** against the best version. So "v2 is better" is a measured claim, not a vibe.

## Quickstart

```bash
bash scripts/setup.sh            # user-space Python/PostgreSQL/Node, virtualenv `Aopx`, database
source Aopx/bin/activate
bash scripts/serve.sh            # PostgreSQL + API on :8000   (terminal 1)
python -m demo.run --runs 40     # traced demo agent runs       (terminal 2)
DEMO_FAKE_LLM=1 python -m demo.run --runs 100   # offline, no API key needed
```

## Demo agent
`demo/` is a LangGraph finance agent (ticker lookup, prices, FX, calculator) answering questions with known answers, so every run gets an objective success label. Market-data tools fail with configurable timeouts and latency spikes, and two prompt versions behave measurably differently.

## Roadmap
- [x] Phase 1: SDK, collector, data model, statistics API, demo agent with fault injection
- [ ] Phase 2: self-hosted LLM on GPU (vLLM) with GPU-aware tracing: TTFT, tokens/s, KV-cache, GPU memory
- [ ] Phase 3: dashboard: runs, trace waterfall, graph view, prompt comparison, cost and latency charts
- [ ] Phase 4: AI root-cause analyst (failure clustering), chaos testing, run replay
- [ ] Phase 5: Docker Compose, migrations, tests, demo GIF
