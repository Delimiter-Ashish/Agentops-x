"""AgentOps-X SDK core.

Design rules:
  * Never break the agent. Export happens on a background thread; every SDK error is swallowed.
  * Never block the agent. Events go into a bounded queue; if the collector is down, events are dropped
    (and counted), not buffered forever.
  * Batches go to the collector as JSON over HTTP: POST {endpoint}/v1/ingest
"""
import atexit
import datetime as dt
import logging
import os
import queue
import threading
import time
import uuid

import httpx

log = logging.getLogger("agentops")

_MAX_FIELD_CHARS = 4000


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clip(value, limit=_MAX_FIELD_CHARS):
    """Make a value JSON-safe and bounded in size."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"... [+{len(value) - limit} chars]"
    if isinstance(value, dict):
        return {str(k): clip(v, limit) for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [clip(v, limit) for v in list(value)[:50]]
    content = getattr(value, "content", None)  # LangChain messages
    if content is not None:
        return {"type": type(value).__name__, "content": clip(content, limit)}
    return clip(repr(value), limit)


class Exporter:
    def __init__(self, endpoint, api_key=None, batch_size=200, flush_interval=0.5, max_queue=20000):
        self.endpoint = endpoint.rstrip("/")
        self.headers = {"X-AgentOps-Key": api_key} if api_key else {}
        self.batch_size, self.flush_interval = batch_size, flush_interval
        self.q = queue.Queue(maxsize=max_queue)
        self.dropped = 0
        self._warned = False
        self._client = httpx.Client(timeout=10)
        self._idle = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="agentops-exporter", daemon=True)
        self._thread.start()

    def emit(self, event):
        try:
            self.q.put_nowait(event)
        except queue.Full:
            self.dropped += 1

    def _loop(self):
        while True:
            batch = []
            try:
                batch.append(self.q.get(timeout=self.flush_interval))
                while len(batch) < self.batch_size:
                    batch.append(self.q.get_nowait())
            except queue.Empty:
                pass
            if batch:
                self._idle.clear()
                self._send(batch)
                for _ in batch:
                    self.q.task_done()
            if self.q.empty():
                self._idle.set()

    def _send(self, batch):
        for attempt in range(3):
            try:
                r = self._client.post(f"{self.endpoint}/v1/ingest", json={"events": batch}, headers=self.headers)
                if r.status_code < 300:
                    return
                if r.status_code < 500:  # client error: retrying won't help
                    log.warning("agentops: collector rejected batch (%s): %s", r.status_code, r.text[:300])
                    return
            except httpx.HTTPError as e:
                if not self._warned:
                    log.warning("agentops: collector unreachable at %s (%s)", self.endpoint, e)
                    self._warned = True
            time.sleep(0.5 * 2 ** attempt)
        self.dropped += len(batch)

    def flush(self, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.q.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return False


_exporter = None


def init(endpoint=None, api_key=None):
    """Start the SDK. Safe to call more than once."""
    global _exporter
    if _exporter is None:
        endpoint = endpoint or os.environ.get("AGENTOPS_ENDPOINT", "http://127.0.0.1:8000")
        api_key = api_key or os.environ.get("AGENTOPS_API_KEY")
        _exporter = Exporter(endpoint, api_key)
        atexit.register(lambda: _exporter.flush(5))
    return _exporter


def flush(timeout=10.0):
    return _exporter.flush(timeout) if _exporter else True


def emit(event):
    if _exporter is None:
        init()
    _exporter.emit(event)


class Run:
    """One execution of an agent. Use as a context manager:

        with agentops.run("fin-agent", input=q, prompt_version=("v2", PROMPT)) as run:
            out = graph.invoke(..., config={"callbacks": [run.callback]})
            run.set_output(out)
            run.mark_success(check(out))
    """

    def __init__(self, agent, input=None, prompt_version=None, tags=None, metadata=None):
        from agentops.langgraph import AgentOpsCallback  # local import: langchain is optional for the core

        self.id = str(uuid.uuid4())
        self.agent = agent
        self.input = input
        self.prompt_version = prompt_version
        self.tags = list(tags or [])
        self.metadata = dict(metadata or {})
        self.output = None
        self.task_success = None
        self.failure_reason = None
        self.callback = AgentOpsCallback(self)

    def __enter__(self):
        pv = None
        if self.prompt_version:
            name, template = self.prompt_version
            pv = {"name": name, "template": template}
        emit({"type": "run_start", "id": self.id, "agent": self.agent, "input": clip(self.input),
              "prompt_version": pv, "tags": self.tags, "metadata": clip(self.metadata),
              "started_at": now_iso()})
        return self

    def set_output(self, output):
        self.output = output

    def mark_success(self, success, reason=None):
        self.task_success = bool(success)
        self.failure_reason = None if success else (reason or "task_failed")

    def __exit__(self, exc_type, exc, tb):
        try:
            self.callback.close_dangling(exc)
            if exc is not None:
                status, error_type = "error", exc_type.__name__
                reason = f"{exc_type.__name__}: {str(exc)[:500]}"
            elif self.task_success is False:
                status, error_type, reason = "failure", None, self.failure_reason
            else:
                status, error_type, reason = "success", None, None
            emit({"type": "run_end", "id": self.id, "status": status, "ended_at": now_iso(),
                  "output": clip(self.output), "task_success": self.task_success,
                  "failure_reason": reason, "error_type": error_type})
        except Exception:  # never break the agent
            log.debug("agentops: run_end failed", exc_info=True)
        return False


def run(agent, **kwargs):
    return Run(agent, **kwargs)
