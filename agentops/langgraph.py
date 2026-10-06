"""LangGraph instrumentation via LangChain callbacks.

Span kinds:
  graph : one graph invocation (root)
  node  : one execution of a LangGraph node; re-executions in the same step are retries (attempt > 1)
  llm   : one model call (tokens, cost, time-to-first-token when streaming)
  tool  : one tool call (a tool that returns "ERROR..." counts as a soft failure)

Internal LangChain runnables (sequences, branches, parsers) are not stored; their children are
re-attached to the nearest stored ancestor, so the trace stays readable.
"""
import json
import threading
import time

import psutil
from langchain_core.callbacks import BaseCallbackHandler

from agentops.pricing import token_cost
from agentops.tracer import clip, emit, now_iso

_PROC = psutil.Process()


def _rss_mb():
    try:
        return _PROC.memory_info().rss / 2**20
    except Exception:
        return None


def _json_size(obj):
    try:
        return len(json.dumps(obj, default=str))
    except Exception:
        return None


class AgentOpsCallback(BaseCallbackHandler):
    raise_error = False  # an SDK bug must never break the agent

    def __init__(self, run):
        self.run = run
        self.spans = {}      # langchain run_id -> open span
        self.alias = {}      # skipped langchain run_id -> nearest stored ancestor span id
        self.attempts = {}   # (parent, node, step) -> executions seen
        self.lock = threading.Lock()

    # ---------- helpers ----------
    def _resolve(self, parent_run_id):
        if parent_run_id is None:
            return None
        pid = str(parent_run_id)
        return pid if pid in self.spans else self.alias.get(pid)

    def _open(self, run_id, parent_run_id, kind, name, input=None, **attrs):
        span = {"type": "span", "id": str(run_id), "run_id": self.run.id,
                "parent_id": self._resolve(parent_run_id), "kind": kind, "name": name,
                "started_at": now_iso(), "_t0": time.perf_counter(), "input": clip(input),
                "attempt": attrs.pop("attempt", 1), "model": attrs.pop("model", None), "attributes": attrs}
        with self.lock:
            self.spans[str(run_id)] = span
        return span

    def _close(self, run_id, status, output=None, error=None, **fields):
        with self.lock:
            span = self.spans.pop(str(run_id), None)
        if span is None:
            return
        t0 = span.pop("_t0")
        first_token = span.pop("_first_token", None)
        span.update(status=status, ended_at=now_iso(), latency_ms=(time.perf_counter() - t0) * 1000,
                    output=clip(output), error=error, memory_mb=_rss_mb(), **fields)
        if first_token is not None:
            span["ttft_ms"] = (first_token - t0) * 1000
        emit(span)

    @staticmethod
    def _err(error):
        return {"type": type(error).__name__, "message": str(error)[:2000]}

    def close_dangling(self, exc=None):
        """Called when the run ends: anything still open was interrupted."""
        for run_id in list(self.spans):
            self._close(run_id, "error", error=self._err(exc) if exc else {"type": "Interrupted", "message": ""})

    # ---------- chains: graph + nodes ----------
    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, tags=None, metadata=None, **kw):
        metadata = metadata or {}
        name = kw.get("name") or (serialized or {}).get("name") or "chain"
        if parent_run_id is None:
            self._open(run_id, None, "graph", name, inputs)
            return
        node = metadata.get("langgraph_node")
        is_node = node is not None and name == node and not name.startswith("__")
        parent = self._resolve(parent_run_id)
        if is_node and not (parent in self.spans and self.spans[parent]["name"] == name):
            key = (parent, name, metadata.get("langgraph_step"))
            with self.lock:
                self.attempts[key] = attempt = self.attempts.get(key, 0) + 1
            self._open(run_id, parent_run_id, "node", name, inputs, attempt=attempt,
                       step=metadata.get("langgraph_step"))
        else:
            with self.lock:
                self.alias[str(run_id)] = parent

    def on_chain_end(self, outputs, *, run_id, **kw):
        if str(run_id) in self.spans:
            self._close(run_id, "ok", outputs, state_size_bytes=_json_size(outputs))
        else:
            self.alias.pop(str(run_id), None)

    def on_chain_error(self, error, *, run_id, **kw):
        if str(run_id) in self.spans:
            self._close(run_id, "error", error=self._err(error))
        else:
            self.alias.pop(str(run_id), None)

    # ---------- LLM calls ----------
    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kw):
        params = kw.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name") or (serialized or {}).get("name")
        flat = messages[0] if messages else []
        self._open(run_id, parent_run_id, "llm", model or "llm", [clip(m, 1500) for m in flat[-6:]],
                   model=model, n_messages=len(flat), temperature=params.get("temperature"))

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kw):
        params = kw.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name") or (serialized or {}).get("name")
        self._open(run_id, parent_run_id, "llm", model or "llm", prompts[-1:] if prompts else None, model=model)

    def on_llm_new_token(self, token, *, run_id, **kw):
        span = self.spans.get(str(run_id))
        if span is not None and "_first_token" not in span:
            span["_first_token"] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kw):
        span = self.spans.get(str(run_id))
        if span is None:
            return
        p_tok = c_tok = None
        output = None
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                p_tok, c_tok = usage.get("input_tokens"), usage.get("output_tokens")
            output = {"content": clip(getattr(msg, "content", None) or gen.text, 3000),
                      "tool_calls": [{"name": t.get("name"), "args": clip(t.get("args"), 500)}
                                     for t in (getattr(msg, "tool_calls", None) or [])]}
        except (IndexError, AttributeError):
            pass
        if p_tok is None and response.llm_output:
            usage = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
            p_tok, c_tok = usage.get("prompt_tokens"), usage.get("completion_tokens")
        self._close(run_id, "ok", output, prompt_tokens=p_tok, completion_tokens=c_tok,
                    cost_usd=token_cost(span.get("model"), p_tok, c_tok))

    def on_llm_error(self, error, *, run_id, **kw):
        self._close(run_id, "error", error=self._err(error))

    def on_retry(self, retry_state, *, run_id, **kw):
        span = self.spans.get(str(run_id))
        if span is not None:
            span["attributes"]["client_retries"] = span["attributes"].get("client_retries", 0) + 1

    # ---------- tools ----------
    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, inputs=None, **kw):
        name = kw.get("name") or (serialized or {}).get("name") or "tool"
        self._open(run_id, parent_run_id, "tool", name, inputs if inputs is not None else input_str)

    def on_tool_end(self, output, *, run_id, **kw):
        content = getattr(output, "content", output)
        text = content if isinstance(content, str) else str(content)
        if text.lstrip().upper().startswith("ERROR"):
            self._close(run_id, "error", text, error={"type": "ToolReturnedError", "message": text[:2000]})
        else:
            self._close(run_id, "ok", text)

    def on_tool_error(self, error, *, run_id, **kw):
        self._close(run_id, "error", error=self._err(error))
