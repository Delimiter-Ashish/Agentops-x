# AgentOps-X 🔭

**Observability and reliability engineering for production LangGraph agents.**

An agent can look great in a demo and still fail quietly across real executions. When it does, was it a tool call, a prompt change, a retry storm, latency, cost, or the agent's state? AgentOps-X makes every execution traceable so you can answer that with data.

> Status: **Phase 3, dashboard.** Trace waterfall, model and prompt comparison with statistics, live GPU view.

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
        │                                                                 ▲    │
        └──► LLM: hosted API or self-hosted vLLM ◄── GPU telemetry agent ─┘    │
                                                  (NVML + vLLM /metrics)       │
                          query API: runs · traces · prompt versions · models · failures · GPU timeseries
```

**Data model:** `prompt_versions 1─* runs 1─* spans` (spans form a tree via `parent_id`). Prompt versions are content-addressed (SHA-256 of the template), so editing a prompt automatically creates a new version. Every ingest is an idempotent upsert on client-generated UUIDs, so retried batches never duplicate data. Run aggregates (tokens, cost, retries, tool errors, peak memory) are computed server-side from spans in the same transaction as `run_end`.

## Dashboard
`http://127.0.0.1:8000/` (built with `bash scripts/build_dashboard.sh`; React, TypeScript, Recharts)

| Page | What it answers |
|---|---|
| **Overview** | How reliable is this agent, what does each correct answer cost, why do runs fail, and which tool is the weakest? |
| **Runs** | Every execution, filterable by outcome, prompt version and model |
| **Run trace** | A waterfall of the whole execution: graph nodes, LLM calls (with time to first token), tool calls, retried attempts and failures, plus an inspector with inputs, outputs, errors, tokens, cost and the GPU state during each LLM call |
| **Compare** | Models and prompt versions side by side: success with 95% confidence intervals, a plain-language verdict on whether the gap is statistically significant, latency, and cost per successful run |
| **GPU** | Live utilization, memory, KV cache, running and queued requests, throughput and power |

## GPU-aware tracing for self-hosted LLMs
Most agent observability stops at the API boundary. When the model runs on your own GPU, AgentOps-X goes further:

| Signal | Source |
|---|---|
| **Time to first token, decode tokens/s** per LLM call | streamed responses, measured in the SDK |
| **GPU utilization, memory, power, temperature** | NVML, sampled at 1 Hz by `agentops.gpu` |
| **KV-cache usage, running / queued requests, server token throughput** | vLLM Prometheus `/metrics` |
| **GPU context of each call** | samples aligned to the call's time window: was it slow because the GPU was saturated or the queue was full? |
| **Batching-aware GPU cost** | `latency x GPU $/s / average concurrent requests`, so a call served alongside 4 others is charged a fifth of the GPU |

`GET /api/models?agent=...` compares the models an agent ran on head to head: success rate with confidence intervals, p50/p95 latency, TTFT, tokens/s, and cost per run. That answers "is the self-hosted model good enough, and what does it really cost?" with data.

```bash
bash scripts/setup_gpu.sh                     # separate venv for the vLLM server
bash scripts/llm.sh                           # serve the model (OpenAI-compatible, tool calling)
python -m agentops.gpu                        # GPU + vLLM telemetry agent
python -m demo.run --llm local --runs 30      # same agent, self-hosted model
python -m demo.run models                     # hosted vs self-hosted, head to head
```

## Prompt version comparison with statistics
`GET /api/prompt-versions?agent=fin-agent` returns success rate with a **95% Wilson confidence interval**, p50/p95 latency, cost per run, retries, and tool errors for each version, plus a **two-proportion z-test p-value** against the best version. So "v2 is better" is a measured claim, not a vibe.

## Quickstart

```bash
bash scripts/setup.sh            # user-space Python/PostgreSQL/Node, virtualenv `Aopx`, database
source Aopx/bin/activate
bash scripts/build_dashboard.sh  # React dashboard (once)
bash scripts/serve.sh            # PostgreSQL + API + dashboard on :8000   (terminal 1)
python -m demo.run --runs 40     # traced demo agent runs       (terminal 2)
DEMO_FAKE_LLM=1 python -m demo.run --runs 100   # offline, no API key needed
```

## Demo agent
`demo/` is a LangGraph finance agent (ticker lookup, prices, FX, calculator) answering questions with known answers, so every run gets an objective success label. Market-data tools fail with configurable timeouts and latency spikes, and two prompt versions behave measurably differently.

## Roadmap
- [x] Phase 1: SDK, collector, data model, statistics API, demo agent with fault injection
- [x] Phase 2: self-hosted LLM on GPU (vLLM), GPU-aware tracing, batching-aware GPU cost, model head-to-head
- [x] Phase 3: dashboard: overview, run explorer, trace waterfall, model and prompt comparison, live GPU view
- [ ] Phase 4: AI root-cause analyst (failure clustering), chaos testing, run replay
- [ ] Phase 5: Docker Compose, migrations, tests, demo GIF
