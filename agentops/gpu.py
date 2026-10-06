"""GPU telemetry agent: samples the GPU (NVML) and the inference server (vLLM /metrics) once a second
and ships the samples to the collector, so every LLM call can be lined up with the hardware state.

    python -m agentops.gpu --vllm-url http://127.0.0.1:8001
"""
import argparse
import datetime as dt
import os
import re
import socket
import time

import httpx

# vLLM has renamed metrics across versions; the first name found wins.
VLLM_METRICS = {
    "kv_cache": ["vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"],
    "running": ["vllm:num_requests_running"],
    "waiting": ["vllm:num_requests_waiting"],
    "gen_tokens": ["vllm:generation_tokens_total"],
    "prompt_tokens": ["vllm:prompt_tokens_total"],
}
_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eE]+|NaN|\+Inf|-Inf)\s*$")


def parse_prometheus(text):
    """Sum each metric over all its label sets."""
    totals = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            try:
                totals[m.group(1)] = totals.get(m.group(1), 0.0) + float(m.group(3))
            except ValueError:
                pass
    return totals


def pick(metrics, names):
    for n in names:
        if n in metrics:
            return metrics[n]
    return None


class NvmlProbe:
    def __init__(self, index):
        import pynvml
        self.nv = pynvml
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        name = pynvml.nvmlDeviceGetName(self.handle)
        self.name = name.decode() if isinstance(name, bytes) else name
        self.index = index

    def read(self):
        nv, h = self.nv, self.handle
        mem = nv.nvmlDeviceGetMemoryInfo(h)
        out = {"gpu_index": self.index, "gpu_name": self.name,
               "util_pct": float(nv.nvmlDeviceGetUtilizationRates(h).gpu),
               "mem_used_mb": mem.used / 2**20, "mem_total_mb": mem.total / 2**20}
        try:
            out["power_w"] = nv.nvmlDeviceGetPowerUsage(h) / 1000
            out["temp_c"] = float(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))
        except nv.NVMLError:
            pass
        return out


def default_gpu_index():
    first = os.environ.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0].strip()
    return int(first) if first.isdigit() else 0


def main():
    ap = argparse.ArgumentParser(description="AgentOps-X GPU telemetry agent")
    ap.add_argument("--endpoint", default=os.environ.get("AGENTOPS_ENDPOINT", "http://127.0.0.1:8000"))
    ap.add_argument("--vllm-url", default=os.environ.get("VLLM_URL", "http://127.0.0.1:8001"))
    ap.add_argument("--gpu-index", type=int, default=None, help="NVML index (default: first CUDA_VISIBLE_DEVICES)")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    headers = {"X-AgentOps-Key": os.environ["AGENTOPS_API_KEY"]} if os.environ.get("AGENTOPS_API_KEY") else {}
    gpu = NvmlProbe(args.gpu_index if args.gpu_index is not None else default_gpu_index())
    client = httpx.Client(timeout=5)
    host = socket.gethostname()
    print(f"sampling {gpu.name} (index {gpu.index}) + {args.vllm_url}/metrics every {args.interval}s "
          f"-> {args.endpoint}  (Ctrl+C to stop)")

    prev = None  # (time, gen_total, prompt_total) for token throughput
    buffer, last_send, warned = [], time.time(), False
    while True:
        t = time.time()
        sample = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "host": host, **gpu.read()}
        try:
            m = parse_prometheus(client.get(f"{args.vllm_url}/metrics").text)
            kv = pick(m, VLLM_METRICS["kv_cache"])
            sample.update(kv_cache_pct=None if kv is None else kv * 100,
                          requests_running=pick(m, VLLM_METRICS["running"]),
                          requests_waiting=pick(m, VLLM_METRICS["waiting"]))
            gen, prompt = pick(m, VLLM_METRICS["gen_tokens"]), pick(m, VLLM_METRICS["prompt_tokens"])
            if prev and gen is not None and t > prev[0]:
                sample["gen_tokens_per_s"] = max(0.0, (gen - prev[1]) / (t - prev[0]))
                if prompt is not None and prev[2] is not None:
                    sample["prompt_tokens_per_s"] = max(0.0, (prompt - prev[2]) / (t - prev[0]))
            prev = (t, gen, prompt) if gen is not None else None
        except httpx.HTTPError:
            prev = None  # inference server not up: still record GPU-only samples
        buffer.append(sample)
        if time.time() - last_send >= 2 or len(buffer) >= 50:
            try:
                client.post(f"{args.endpoint}/v1/gpu", json={"samples": buffer}, headers=headers).raise_for_status()
                buffer, warned = [], False
            except httpx.HTTPError as e:
                if not warned:
                    print(f"collector unreachable ({e}); buffering")
                    warned = True
                buffer = buffer[-600:]  # keep at most ~10 minutes
            last_send = time.time()
        time.sleep(max(0.0, args.interval - (time.time() - t)))


if __name__ == "__main__":
    main()
