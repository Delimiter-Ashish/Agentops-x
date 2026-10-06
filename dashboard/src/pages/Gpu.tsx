import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, type GpuSample } from "../api";
import { useData } from "../useData";
import { Failed, Kpi, Loading } from "../components/bits";
import { num, time } from "../format";

const AXIS = { stroke: "#5c718c", fontSize: 12 };
const TIP = { contentStyle: { background: "#1b2e48", border: "1px solid #263b55", borderRadius: 8 }, labelStyle: { color: "#8ea2bb" } };

function Panel({ title, data, lines, unit, max }: {
  title: string; data: Record<string, unknown>[]; unit?: string; max?: number;
  lines: { key: string; color: string; label: string }[];
}) {
  return (
    <div className="chart-box">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={190}>
        <LineChart data={data}>
          <CartesianGrid stroke="#263b55" vertical={false} />
          <XAxis dataKey="t" {...AXIS} minTickGap={40} />
          <YAxis {...AXIS} unit={unit} domain={[0, max ?? "auto"]} width={52} />
          <Tooltip {...TIP} formatter={(v: number, n: string) => [`${num(v, 1)}${unit ?? ""}`, lines.find((l) => l.key === n)?.label ?? n]} />
          {lines.map((l) => <Line key={l.key} dataKey={l.key} stroke={l.color} strokeWidth={1.8} dot={false} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Gpu() {
  const { data, error } = useData(() => get<GpuSample[]>("gpu/timeseries", { minutes: 15 }), [], 3000);
  if (error) return <Failed error={error} />;
  if (!data) return <Loading />;
  if (data.length === 0) return (
    <>
      <h1>GPU</h1>
      <div className="empty">No GPU telemetry in the last 15 minutes. Start the telemetry agent with <span className="mono">python -m agentops.gpu</span> next to your inference server.</div>
    </>
  );
  const last = data[data.length - 1];
  const rows = data.map((s) => ({
    t: time(s.ts), util: s.util_pct, kv: s.kv_cache_pct, running: s.requests_running, waiting: s.requests_waiting,
    gen: s.gen_tokens_per_s, mem: s.mem_used_mb == null ? null : s.mem_used_mb / 1024, power: s.power_w,
  }));
  return (
    <>
      <h1>GPU</h1>
      <p className="lede">{last.gpu_name ?? "GPU"} and the inference server, sampled every second over the last 15 minutes. Updates live.</p>
      <div className="kpis">
        <Kpi label="Utilization" value={`${num(last.util_pct)}%`} />
        <Kpi label="Memory" value={`${num((last.mem_used_mb ?? 0) / 1024, 1)} GB`} sub={last.mem_total_mb ? `of ${num(last.mem_total_mb / 1024)} GB` : undefined} />
        <Kpi label="KV cache used" value={last.kv_cache_pct == null ? "–" : `${num(last.kv_cache_pct, 1)}%`} />
        <Kpi label="Requests running / queued" value={`${num(last.requests_running)} / ${num(last.requests_waiting)}`} />
        <Kpi label="Generation" value={last.gen_tokens_per_s == null ? "–" : `${num(last.gen_tokens_per_s)} tok/s`} />
      </div>
      <div className="grid2 section">
        <Panel title="Utilization" data={rows} unit="%" max={100} lines={[{ key: "util", color: "#3fc1a5", label: "GPU utilization" }]} />
        <Panel title="Server throughput" data={rows} lines={[{ key: "gen", color: "#7fa8f5", label: "generated tokens/s" }]} />
        <Panel title="Requests running (teal) and queued (amber)" data={rows} lines={[{ key: "running", color: "#3fc1a5", label: "running" }, { key: "waiting", color: "#f0a63a", label: "queued" }]} />
        <Panel title="KV cache used" data={rows} unit="%" max={100} lines={[{ key: "kv", color: "#c49cf0", label: "KV cache" }]} />
        <Panel title="Memory" data={rows} unit=" GB" lines={[{ key: "mem", color: "#7fa8f5", label: "GPU memory" }]} />
        <Panel title="Power" data={rows} unit=" W" lines={[{ key: "power", color: "#ee6a64", label: "power draw" }]} />
      </div>
    </>
  );
}
