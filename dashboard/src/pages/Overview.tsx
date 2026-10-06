import { CartesianGrid, ComposedChart, Bar, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, type Failures, type Summary, type TimePoint } from "../api";
import { useData } from "../useData";
import { Failed, Kpi, Loading, StatusDot } from "../components/bits";
import { num, pct, secs, time, usd } from "../format";

const AXIS = { stroke: "#5c718c", fontSize: 12 };
const TIP = { contentStyle: { background: "#1b2e48", border: "1px solid #263b55", borderRadius: 8 }, labelStyle: { color: "#8ea2bb" } };

export default function Overview({ agent }: { agent: string }) {
  const sum = useData(() => get<Summary>("summary", { agent }), [agent], 10000);
  const ts = useData(() => get<TimePoint[]>("timeseries", { agent, bucket: "minute" }), [agent], 10000);
  const fail = useData(() => get<Failures>("failures", { agent }), [agent], 10000);

  if (sum.error) return <Failed error={sum.error} />;
  const s = sum.data;
  if (!s) return <Loading />;

  const worst = fail.data?.by_tool.filter((t) => (t.error_rate ?? 0) > 0).sort((a, b) => (b.error_rate ?? 0) - (a.error_rate ?? 0))[0];
  return (
    <>
      <h1>{agent}</h1>
      <p className="lede">{num(s.runs)} finished runs. A run counts as a success only when the task checker accepts its answer, so crashes and wrong answers both count against it.</p>

      <div className="kpis">
        <Kpi label="Task success" value={pct(s.success_rate)} sub={`95% CI ${pct(s.success_ci95[0])} to ${pct(s.success_ci95[1])}`} />
        <Kpi label="Latency p50 / p95" value={secs(s.p50_latency_ms)} sub={`p95 ${secs(s.p95_latency_ms)}`} />
        <Kpi label="Cost per successful run" value={usd(s.cost_per_success_usd)} sub={`${usd(s.avg_cost_usd)} per run, ${usd(s.total_cost_usd)} total`} />
        <Kpi label="Retries / tool errors" value={`${num(s.retries)} / ${num(s.tool_errors)}`} sub={`${num(s.errors)} runs crashed`} />
      </div>

      {worst && (
        <p className="callout section">
          The least reliable tool is <b>{worst.tool}</b>: {pct(worst.error_rate)} of its {num(worst.calls)} calls failed
          (p95 latency {secs(worst.p95_latency_ms)}).
        </p>
      )}

      <section className="section">
        <h2>Success rate (line) and p95 latency (bars) per minute</h2>
        {ts.data && ts.data.length > 0 ? (
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={ts.data.map((p) => ({ ...p, t: time(p.t), success: p.success_rate == null ? null : p.success_rate * 100, p95: p.p95_latency_ms == null ? null : p.p95_latency_ms / 1000 }))}>
                <CartesianGrid stroke="#263b55" vertical={false} />
                <XAxis dataKey="t" {...AXIS} />
                <YAxis yAxisId="l" domain={[0, 100]} unit="%" {...AXIS} />
                <YAxis yAxisId="r" orientation="right" unit="s" {...AXIS} />
                <Tooltip {...TIP} formatter={(v: number, n: string) => (n === "success" ? [`${v.toFixed(0)}%`, "success"] : [`${v.toFixed(1)} s`, "p95 latency"])} />
                <Bar yAxisId="r" dataKey="p95" fill="#4d6889" radius={[3, 3, 0, 0]} maxBarSize={28} />
                <Line yAxisId="l" dataKey="success" stroke="#3fc1a5" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : <div className="empty">No finished runs in this period.</div>}
      </section>

      <div className="grid2 section">
        <section>
          <h2>Why runs fail</h2>
          {fail.data && fail.data.by_reason.length ? (
            <div className="table-wrap"><table>
              <thead><tr><th>Outcome</th><th>Cause</th><th className="num">Runs</th></tr></thead>
              <tbody>{fail.data.by_reason.map((r) => (
                <tr key={r.status + r.type} className="click" onClick={() => (location.hash = `/runs?status=${r.status}`)}>
                  <td><StatusDot status={r.status} label={r.status === "error" ? "Crashed" : "Wrong answer"} /></td>
                  <td title={r.example ?? ""}>{r.type === "wrong_answer" ? "Checker rejected the answer" : r.type}</td>
                  <td className="num">{r.count}</td>
                </tr>))}</tbody>
            </table></div>
          ) : <div className="empty">No failed runs yet.</div>}
        </section>
        <section>
          <h2>Tool health</h2>
          {fail.data && fail.data.by_tool.length ? (
            <div className="table-wrap"><table>
              <thead><tr><th>Tool</th><th className="num">Calls</th><th className="num">Error rate</th><th className="num">p95</th></tr></thead>
              <tbody>{fail.data.by_tool.map((t) => (
                <tr key={t.tool}>
                  <td>{t.tool}</td><td className="num">{num(t.calls)}</td>
                  <td className="num" style={{ color: (t.error_rate ?? 0) > 0.1 ? "var(--err)" : undefined }}>{pct(t.error_rate, 1)}</td>
                  <td className="num">{secs(t.p95_latency_ms)}</td>
                </tr>))}</tbody>
            </table></div>
          ) : <div className="empty">No tool calls recorded.</div>}
        </section>
      </div>

    </>
  );
}
