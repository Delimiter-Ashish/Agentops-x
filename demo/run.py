"""Run the demo agent many times, alternating prompt versions, with every run traced.

    python -m demo.run --runs 40 --prompts v1 v2 --concurrency 2
    DEMO_FAKE_LLM=1 python -m demo.run --runs 100      # offline, no API key
"""
import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()

import agentops  # noqa: E402
from demo.agent import AGENT_NAME, PROMPTS, build_graph, make_llm  # noqa: E402
from demo.tasks import check, make_tasks  # noqa: E402


def run_one(graphs, version, task):
    t0 = time.time()
    status, got = "?", None
    try:
        with agentops.run(AGENT_NAME, input={"question": task["question"]},
                          prompt_version=(version, PROMPTS[version]), tags=[f"prompt:{version}"],
                          metadata={"expected": task["expected"]}) as run:
            result = graphs[version].invoke({"messages": [HumanMessage(task["question"])]},
                                            config={"callbacks": [run.callback], "recursion_limit": 14})
            answer = result["messages"][-1].text  # str even when content is a list of blocks (Gemini 3)
            ok, got = check(answer, task["expected"])
            run.set_output({"answer": answer, "parsed": got})
            run.mark_success(ok, None if ok else f"wrong answer: got {got}, expected {task['expected']}")
            status = "success" if ok else "failure"
    except Exception as e:  # recorded by the SDK as an errored run
        status = f"error ({type(e).__name__})"
    return version, status, time.time() - t0, got, task["expected"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=40)
    ap.add_argument("--prompts", nargs="+", default=list(PROMPTS))
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--llm", choices=["env", "local"], default="env",
                    help="env: LLM_* settings from .env (e.g. Gemini); local: self-hosted vLLM server")
    args = ap.parse_args()

    agentops.init()
    llm = make_llm(None if args.llm == "env" else args.llm)
    graphs = {v: build_graph(llm, PROMPTS[v]) for v in args.prompts}
    tasks = make_tasks(args.runs, seed=args.seed)
    jobs = [(args.prompts[i % len(args.prompts)], t) for i, t in enumerate(tasks)]
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None) or type(llm).__name__
    print(f"{len(jobs)} runs | prompts {args.prompts} | model {model}\n")

    icons = {"success": "✓", "failure": "✗"}
    with ThreadPoolExecutor(args.concurrency) as ex:
        for i, (v, status, secs, got, exp) in enumerate(ex.map(lambda j: run_one(graphs, *j), jobs), 1):
            print(f"[{i:3d}/{len(jobs)}] {icons.get(status, '!')} {v}  {secs:5.1f}s  {status:<26} got={got} expected={exp}")

    agentops.flush()
    endpoint = os.environ.get("AGENTOPS_ENDPOINT", "http://127.0.0.1:8000")
    rows = (httpx.get(f"{endpoint}/api/prompt-versions", params={"agent": AGENT_NAME, "model": model}).json()
            or httpx.get(f"{endpoint}/api/prompt-versions", params={"agent": AGENT_NAME}).json())
    print(f"\nprompt version comparison for {model} (all runs so far)")
    print(f"{'version':<8}{'runs':>6}{'success':>10}{'95% CI':>16}{'p50 s':>8}{'p95 s':>8}{'retries':>9}"
          f"{'tool err':>10}{'$/run':>10}{'p vs best':>11}")
    for r in rows:
        lo, hi = r["success_ci95"]
        pv = r.get("p_value_vs_best")
        print(f"{r['prompt_version']:<8}{r['runs']:>6}{r['success_rate'] or 0:>10.0%}"
              f"{f'{lo:.0%}-{hi:.0%}':>16}{(r['p50_latency_ms'] or 0) / 1000:>8.1f}"
              f"{(r['p95_latency_ms'] or 0) / 1000:>8.1f}{r['avg_retries'] or 0:>9.2f}"
              f"{r['avg_tool_errors'] or 0:>10.2f}{r['avg_cost_usd'] or 0:>10.5f}"
              f"{'best' if pv is None else f'{pv:.3f}':>11}")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["models"]:   # python -m demo.run models  -> model head-to-head table
        print_models()
    else:
        main()


def print_models():
    endpoint = os.environ.get("AGENTOPS_ENDPOINT", "http://127.0.0.1:8000")
    rows = httpx.get(f"{endpoint}/api/models", params={"agent": AGENT_NAME}).json()
    print(f"{'model':<34}{'runs':>6}{'success':>9}{'p50 s':>8}{'p95 s':>8}{'TTFT ms':>9}{'tok/s':>8}{'$/run':>10}")
    for r in rows:
        f = lambda v, fmt: format(v, fmt) if v is not None else "-"  # noqa: E731
        print(f"{r['model'][:33]:<34}{r['runs']:>6}{f(r['success_rate'], '.0%'):>9}"
              f"{f((r['p50_latency_ms'] or 0) / 1000, '.1f'):>8}{f((r['p95_latency_ms'] or 0) / 1000, '.1f'):>8}"
              f"{f(r['p50_ttft_ms'], '.0f'):>9}{f(r['tokens_per_s'], '.0f'):>8}{f(r['avg_cost_usd'], '.5f'):>10}")
