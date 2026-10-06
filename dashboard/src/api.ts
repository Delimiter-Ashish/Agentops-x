// All requests are relative ("api/...") so the dashboard works under any path prefix.
export async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") qs.set(k, String(v));
  const res = await fetch(`api/${path}${qs.toString() ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on api/${path}`);
  return res.json();
}

export type Status = "running" | "success" | "failure" | "error";

export interface Agent { agent: string; runs: number; last_run: string; success_rate: number | null }

export interface Summary {
  runs: number; successes: number; errors: number; success_rate: number | null; success_ci95: [number | null, number | null];
  p50_latency_ms: number | null; p95_latency_ms: number | null; avg_cost_usd: number | null; total_cost_usd: number | null;
  cost_per_success_usd: number | null; retries: number | null; tool_errors: number | null; tokens: number | null;
}

export interface RunRow {
  id: string; agent_name: string; model: string | null; status: Status; task_success: boolean | null;
  failure_reason: string | null; error_type: string | null; started_at: string; ended_at: string | null;
  latency_ms: number | null; llm_calls: number; tool_calls: number; tool_errors: number; retries: number;
  prompt_tokens: number; completion_tokens: number; cost_usd: number; peak_memory_mb: number | null;
  max_state_bytes: number | null; tags: string[] | null; prompt_version: string | null;
}

export interface RunDetail extends RunRow {
  input: unknown; output: unknown; metadata: Record<string, unknown> | null; prompt_template: string | null;
}

export interface GpuContext {
  samples: number; util_pct: number | null; kv_cache_pct: number | null; requests_running: number | null;
  requests_waiting: number | null; mem_used_mb: number | null; power_w: number | null;
}

export interface Span {
  id: string; parent_id: string | null; kind: "graph" | "node" | "llm" | "tool"; name: string; status: "ok" | "error";
  attempt: number; started_at: string; ended_at: string | null; latency_ms: number | null; ttft_ms: number | null;
  model: string | null; prompt_tokens: number | null; completion_tokens: number | null; cost_usd: number | null;
  memory_mb: number | null; state_size_bytes: number | null; input: unknown; output: unknown;
  error: { type: string; message: string } | null; attributes: Record<string, unknown> | null;
  tokens_per_s?: number | null; gpu?: GpuContext | null;
}

export interface Comparison {
  runs: number; successes: number; success_rate: number | null; success_ci95: [number | null, number | null];
  p50_latency_ms: number | null; p95_latency_ms: number | null; avg_cost_usd: number | null;
  cost_per_success_usd: number | null; avg_retries: number | null; p_value_vs_best?: number | null;
}
export interface PromptRow extends Comparison { prompt_version: string; errors: number; avg_tool_errors: number | null; avg_tokens: number | null }
export interface ModelRow extends Comparison { model: string; p50_ttft_ms: number | null; tokens_per_s: number | null; avg_tokens: number | null }

export interface Failures {
  by_reason: { status: string; type: string; count: number; example: string | null }[];
  by_tool: { tool: string; calls: number; errors: number; error_rate: number | null; p95_latency_ms: number | null }[];
}

export interface TimePoint { t: string; runs: number; success_rate: number | null; p95_latency_ms: number | null; cost_usd: number | null }

export interface GpuSample {
  ts: string; gpu_name: string | null; util_pct: number | null; mem_used_mb: number | null; mem_total_mb: number | null;
  power_w: number | null; temp_c: number | null; kv_cache_pct: number | null; requests_running: number | null;
  requests_waiting: number | null; gen_tokens_per_s: number | null; prompt_tokens_per_s: number | null;
}

export interface Alert {
  id: number; created_at: string; agent_name: string; model: string | null; run_id: string | null; span_id: string | null;
  kind: "cost_spike" | "latency_spike" | "runaway_generation" | "budget_exceeded" | string;
  severity: "warning" | "critical"; message: string; value: number | null; baseline: number | null; acknowledged: boolean;
}

export async function post<T>(path: string): Promise<T> {
  const res = await fetch(`api/${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on api/${path}`);
  return res.json();
}
