import { useMemo, useState } from "react";
import { get, type RunDetail, type Span } from "../api";
import { useData } from "../useData";
import { Failed, Loading, StatusDot } from "../components/bits";
import { datetime, num, secs, short, usd } from "../format";

interface Row { span: Span; depth: number; start: number; end: number }

/** Depth-first order of the span tree, children sorted by start time. */
function layout(spans: Span[]): { rows: Row[]; t0: number; total: number } {
  const ids = new Set(spans.map((s) => s.id));
  const kids = new Map<string | null, Span[]>();
  for (const s of spans) {
    const parent = s.parent_id && ids.has(s.parent_id) ? s.parent_id : null;
    kids.set(parent, [...(kids.get(parent) ?? []), s]);
  }
  const t = (iso: string) => new Date(iso).getTime();
  const t0 = Math.min(...spans.map((s) => t(s.started_at)));
  const tEnd = Math.max(...spans.map((s) => (s.ended_at ? t(s.ended_at) : t(s.started_at) + (s.latency_ms ?? 0))));
  const rows: Row[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const s of (kids.get(parent) ?? []).sort((a, b) => t(a.started_at) - t(b.started_at))) {
      const start = t(s.started_at) - t0;
      rows.push({ span: s, depth, start, end: start + (s.latency_ms ?? 0) });
      walk(s.id, depth + 1);
    }
  };
  walk(null, 0);
  return { rows, t0, total: Math.max(1, tEnd - t0) };
}

const json = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v, null, 2));

export default function RunView({ id }: { id: string }) {
  const { data, error } = useData(() => get<{ run: RunDetail; spans: Span[] }>(`runs/${id}`), [id]);
  const [sel, setSel] = useState<string | null>(null);
  const lay = useMemo(() => (data?.spans.length ? layout(data.spans) : null), [data]);

  if (error) return <Failed error={error} />;
  if (!data) return <Loading />;
  const { run, spans } = data;
  const selected = spans.find((s) => s.id === sel) ?? spans.find((s) => s.status === "error" && s.kind !== "graph") ?? spans[0];

  return (
    <>
      <a className="back" href="#/runs">Back to runs</a>
      <h1 style={{ marginTop: 8 }}>Run <span className="mono" style={{ fontSize: 22 }}>{short(run.id)}</span></h1>
      <div className="run-meta">
        <StatusDot status={run.status} label={{ success: "Success", failure: "Wrong answer", error: "Crashed", running: "Running" }[run.status]} />
        <span>Started <b>{datetime(run.started_at)}</b></span>
        <span>Duration <b>{secs(run.latency_ms)}</b></span>
        <span>Prompt <b>{run.prompt_version ?? "–"}</b></span>
        <span>Model <b>{run.model ?? "–"}</b></span>
        <span>Cost <b>{usd(run.cost_usd)}</b></span>
        <span>Retries <b>{run.retries}</b></span>
        <span>Peak memory <b>{run.peak_memory_mb ? `${num(run.peak_memory_mb)} MB` : "–"}</b></span>
      </div>
      {run.failure_reason && <p className="callout">{run.failure_reason}</p>}

      {!lay ? <div className="empty section">This run has no spans.</div> : (
        <div className="trace section">
          <div>
            <div className="wf" role="list" aria-label="Trace timeline">
              <div className="wf-head"><span>Step</span><span>0 to {secs(lay.total)}</span><span style={{ textAlign: "right" }}>Time</span></div>
              {lay.rows.map(({ span: s, depth, start, end }) => {
                const retry = s.kind === "node" && s.attempt > 1;
                const cls = s.status === "error" ? "bad" : retry ? "retry" : s.kind;
                const ttft = s.kind === "llm" && s.ttft_ms && s.latency_ms ? (s.ttft_ms / s.latency_ms) * 100 : null;
                return (
                  <div key={s.id} role="listitem" tabIndex={0} className={`wf-row ${selected?.id === s.id ? "sel" : ""}`}
                    onClick={() => setSel(s.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setSel(s.id)}>
                    <div className="wf-name" style={{ paddingLeft: depth * 14 }}>
                      <span className="wf-kind">{s.kind}</span>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
                      {retry && <span className="tag warn">try {s.attempt}</span>}
                      {s.status === "error" && <span className="tag err">{s.error?.type ?? "error"}</span>}
                    </div>
                    <div className="wf-lane">
                      <div className={`wf-bar ${cls}`} style={{ left: `${(start / lay.total) * 100}%`, width: `${Math.max(0.3, ((end - start) / lay.total) * 100)}%` }}>
                        {ttft != null && <span className="ttft" style={{ width: `${ttft}%` }} />}
                      </div>
                    </div>
                    <div className="wf-dur">{secs(s.latency_ms)}</div>
                  </div>
                );
              })}
            </div>
            <div className="legend">
              <span><i style={{ background: "var(--node)" }} />graph node</span>
              <span><i style={{ background: "var(--llm)" }} />LLM call (light part: time to first token)</span>
              <span><i style={{ background: "var(--tool)" }} />tool call</span>
              <span><i style={{ background: "var(--warn)" }} />retried attempt</span>
              <span><i style={{ background: "var(--err)" }} />failed</span>
            </div>
          </div>
          {selected && <Inspector span={selected} />}
        </div>
      )}
    </>
  );
}

function Inspector({ span: s }: { span: Span }) {
  const attrs = s.attributes ?? {};
  return (
    <aside className="inspector" aria-label="Step details">
      <h2><StatusDot status={s.status} label="" />{s.name}</h2>
      <dl className="kv">
        <dt>Kind</dt><dd>{s.kind}{s.kind === "node" && s.attempt > 1 ? `, attempt ${s.attempt}` : ""}</dd>
        <dt>Duration</dt><dd>{secs(s.latency_ms)}</dd>
        {s.model && <><dt>Model</dt><dd>{s.model}</dd></>}
        {s.ttft_ms != null && <><dt>First token</dt><dd>{secs(s.ttft_ms)}</dd></>}
        {s.tokens_per_s != null && <><dt>Decode speed</dt><dd>{num(s.tokens_per_s)} tokens/s</dd></>}
        {(s.prompt_tokens != null || s.completion_tokens != null) && <><dt>Tokens in / out</dt><dd>{num(s.prompt_tokens)} / {num(s.completion_tokens)}</dd></>}
        {s.cost_usd != null && <><dt>Cost</dt><dd>{usd(s.cost_usd)}{attrs.pricing === "gpu_time" ? ` (GPU time shared by ${Number(attrs.avg_concurrency).toFixed(1)} requests)` : ""}</dd></>}
        {s.memory_mb != null && <><dt>Process memory</dt><dd>{num(s.memory_mb)} MB</dd></>}
        {s.state_size_bytes != null && <><dt>State size</dt><dd>{num(s.state_size_bytes / 1024, 1)} KB</dd></>}
      </dl>
      {s.gpu && (
        <>
          <div className="sub">GPU while this call ran</div>
          <dl className="kv">
            <dt>Utilization</dt><dd>{num(s.gpu.util_pct)}%</dd>
            <dt>KV cache used</dt><dd>{num(s.gpu.kv_cache_pct, 1)}%</dd>
            <dt>Requests running</dt><dd>{num(s.gpu.requests_running, 1)}</dd>
            <dt>Requests queued</dt><dd>{num(s.gpu.requests_waiting, 1)}</dd>
            <dt>GPU memory</dt><dd>{s.gpu.mem_used_mb != null ? `${num(s.gpu.mem_used_mb / 1024, 1)} GB` : "–"}</dd>
          </dl>
        </>
      )}
      {s.error && <><div className="sub">Error</div><pre className="payload" style={{ borderColor: "var(--err)" }}>{s.error.type}: {s.error.message}</pre></>}
      <div className="sub">Input</div><pre className="payload">{json(s.input) || "–"}</pre>
      <div className="sub">Output</div><pre className="payload">{json(s.output) || "–"}</pre>
    </aside>
  );
}
