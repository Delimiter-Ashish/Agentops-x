"""Trigger each kind of alert on purpose, so you can see detection and guardrails working.

    python -m demo.alerts_demo runaway   # self-hosted model writes a huge answer, no cap  -> "Runaway generation" alert
    python -m demo.alerts_demo cap       # same request with a 300-token guardrail        -> stopped mid-stream, "Budget stopped run"
    python -m demo.alerts_demo budget    # finance agent allowed only 2 LLM calls          -> "Budget stopped run"
    python -m demo.alerts_demo budget --llm env   # same, on the model from .env (e.g. Gemini)

Runs are recorded under the agent "alert-demo" so they never skew fin-agent's statistics.
Runaway detection compares against everything this model normally generates, so run some
normal fin-agent traffic on the same model first (you already have).
"""
import argparse
import os
import time

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()

import agentops  # noqa: E402
from demo.agent import PROMPTS, build_graph, make_llm  # noqa: E402
from demo.tasks import make_tasks  # noqa: E402

AGENT = "alert-demo"
LONG_REQUEST = ("Count from 1 to 800, writing every number in English words, one number per line. "
                "Do not skip any number and do not stop early.")


def local_llm(max_tokens=None):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(base_url=f"http://127.0.0.1:{os.environ.get('VLLM_PORT', '8001')}/v1",
                      api_key=os.environ.get("VLLM_API_KEY", "local"),
                      model=os.environ.get("LOCAL_MODEL", "Qwen/Qwen2.5-14B-Instruct"),
                      temperature=0.2, timeout=600, streaming=True, stream_usage=True, max_tokens=max_tokens)


def runaway():
    print("Asking the self-hosted model for a very long answer with NO output cap (takes 1-2 minutes)...")
    t0 = time.time()
    with agentops.run(AGENT, input={"request": LONG_REQUEST}, tags=["scenario:runaway"]) as run:
        msg = local_llm().invoke(LONG_REQUEST, config={"callbacks": run.callbacks})
    out = (msg.usage_metadata or {}).get("output_tokens")
    print(f"done in {time.time() - t0:.0f} s, {out} output tokens")


def cap():
    print("Same request, but with a guardrail: max 300 output tokens per LLM call...")
    t0 = time.time()
    limits = agentops.Limits(max_output_tokens_per_call=300)
    try:
        with agentops.run(AGENT, input={"request": LONG_REQUEST}, tags=["scenario:cap"], limits=limits) as run:
            local_llm().invoke(LONG_REQUEST, config={"callbacks": run.callbacks})
        print("finished without hitting the cap (unexpected)")
    except agentops.BudgetExceeded as e:
        print(f"stopped after {time.time() - t0:.1f} s: {e}")


def budget(profile):
    print("Finance agent with a budget of only 2 LLM calls (a normal answer needs 3-5)...")
    graph = build_graph(make_llm(profile), PROMPTS["v2"])
    task = make_tasks(1, seed=11)[0]
    limits = agentops.Limits(max_llm_calls=2)
    try:
        with agentops.run(AGENT, input={"question": task["question"]}, prompt_version=("v2", PROMPTS["v2"]),
                          tags=["scenario:budget"], limits=limits) as run:
            graph.invoke({"messages": [HumanMessage(task["question"])]},
                         config={"callbacks": run.callbacks, "recursion_limit": 14})
        print("finished within budget (unexpected)")
    except agentops.BudgetExceeded as e:
        print(f"stopped: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["runaway", "cap", "budget"])
    ap.add_argument("--llm", choices=["local", "env"], default="local", help="model for the budget scenario")
    args = ap.parse_args()

    agentops.init()
    {"runaway": runaway, "cap": cap, "budget": lambda: budget(None if args.llm == "env" else "local")}[args.scenario]()
    agentops.flush()
    time.sleep(1)
    endpoint = os.environ.get("AGENTOPS_ENDPOINT", "http://127.0.0.1:8000")
    try:
        alerts = httpx.get(f"{endpoint}/api/alerts", params={"agent": AGENT}).json()
    except httpx.HTTPError:
        print(f"\nCould not reach the AgentOps-X server at {endpoint}. Is scripts/serve.sh running?")
        return
    print(f"\nopen alerts for '{AGENT}': {len(alerts)}")
    for a in alerts[:6]:
        print(f"  [{a['severity']}] {a['kind']}: {a['message']}")
    print("\nIn the dashboard: pick the agent 'alert-demo' in the sidebar, then open Alerts.")


if __name__ == "__main__":
    main()
