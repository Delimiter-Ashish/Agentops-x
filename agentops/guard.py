"""Guardrails: stop a run before it burns money.

    limits = agentops.Limits(max_output_tokens_per_call=2048, max_cost_usd=0.05, max_llm_calls=12)
    with agentops.run("fin-agent", input=q, limits=limits) as run:
        graph.invoke(state, config={"callbacks": run.callbacks})

With a streaming model the per-call token cap is enforced *while the model is still generating*:
the stream is cut off at the limit instead of running to the context window. Budgets for the whole
run (cost, total tokens, number of LLM calls) are checked before every new LLM call.
A breach raises BudgetExceeded, which the tracer records like any other error.
"""
import threading
from dataclasses import dataclass

from langchain_core.callbacks import BaseCallbackHandler

from agentops.pricing import token_cost


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Limits:
    max_output_tokens_per_call: int | None = None
    max_cost_usd: float | None = None
    max_total_tokens: int | None = None
    max_llm_calls: int | None = None


class Guard(BaseCallbackHandler):
    raise_error = True  # unlike the tracer, the guard is *meant* to interrupt the agent

    def __init__(self, limits: Limits):
        self.limits = limits
        self.lock = threading.Lock()
        self.streamed = {}      # run_id -> tokens streamed so far in this call
        self.models = {}        # run_id -> model name
        self.calls = 0
        self.tokens = 0
        self.cost = 0.0

    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self._before_call(run_id, kw)

    def on_llm_start(self, serialized, prompts, *, run_id, **kw):
        self._before_call(run_id, kw)

    def _before_call(self, run_id, kw):
        lim = self.limits
        with self.lock:
            if lim.max_llm_calls is not None and self.calls >= lim.max_llm_calls:
                raise BudgetExceeded(f"run reached its limit of {lim.max_llm_calls} LLM calls")
            if lim.max_cost_usd is not None and self.cost >= lim.max_cost_usd:
                raise BudgetExceeded(f"run spent ${self.cost:.4f}, over its ${lim.max_cost_usd} budget")
            if lim.max_total_tokens is not None and self.tokens >= lim.max_total_tokens:
                raise BudgetExceeded(f"run used {self.tokens:,} tokens, over its {lim.max_total_tokens:,} budget")
            self.calls += 1
            params = kw.get("invocation_params") or {}
            self.models[str(run_id)] = params.get("model") or params.get("model_name")
            self.streamed[str(run_id)] = 0

    def on_llm_new_token(self, token, *, run_id, **kw):
        cap = self.limits.max_output_tokens_per_call
        if cap is None:
            return
        key = str(run_id)
        with self.lock:
            self.streamed[key] = self.streamed.get(key, 0) + 1
            n = self.streamed[key]
        if n > cap:
            raise BudgetExceeded(f"LLM call passed {cap:,} output tokens and was stopped mid-generation")

    def on_llm_end(self, response, *, run_id, **kw):
        p_tok = c_tok = None
        try:
            usage = getattr(response.generations[0][0].message, "usage_metadata", None) or {}
            p_tok, c_tok = usage.get("input_tokens"), usage.get("output_tokens")
        except (IndexError, AttributeError):
            pass
        with self.lock:
            self.tokens += (p_tok or 0) + (c_tok or 0)
            self.cost += token_cost(self.models.pop(str(run_id), None), p_tok, c_tok) or 0.0
            self.streamed.pop(str(run_id), None)
        cap = self.limits.max_output_tokens_per_call
        if cap is not None and c_tok and c_tok > cap:  # non-streaming models: enforce after the call
            raise BudgetExceeded(f"LLM call produced {c_tok:,} output tokens, over the {cap:,} limit")
