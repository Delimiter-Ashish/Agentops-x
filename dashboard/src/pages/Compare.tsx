import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, type Comparison, type ModelRow, type PromptRow } from "../api";
import { useData } from "../useData";
import { CiBar, Failed, Loading } from "../components/bits";
import { num, pval, secs, usd } from "../format";

const AXIS = { stroke: "#5c718c", fontSize: 12 };
const TIP = { contentStyle: { background: "#1b2e48", border: "1px solid #263b55", borderRadius: 8 }, labelStyle: { color: "#8ea2bb" }, cursor: { fill: "rgba(255,255,255,0.04)" } };

/** Plain-language verdict: is the gap between the best and the runner-up real? */
function verdict<T extends Comparison>(rows: T[], name: (r: T) => string) {
  if (rows.length < 2) return null;
  const sorted = [...rows].sort((a, b) => (b.success_rate ?? 0) - (a.success_rate ?? 0));
  const [best, next] = sorted;
  const p = next.p_value_vs_best;
  if (p == null) return null;
  return p < 0.05
    ? `${name(best)} is more reliable than ${name(next)}, and the gap is statistically significant (${pval(p)}).`
    : `${name(best)} is ahead of ${name(next)}, but the difference is not significant yet (${pval(p)}). Run more tasks before deciding.`;
}

function SuccessChart<T extends Comparison>({ rows, name }: { rows: T[]; name: (r: T) => string }) {
  const data = rows.map((r) => {
    const rate = (r.success_rate ?? 0) * 100;
    return { name: name(r), rate, err: [rate - (r.success_ci95[0] ?? 0) * 100, (r.success_ci95[1] ?? 0) * 100 - rate] };
  });
  return (
    <div className="chart-box">
      <h3>Task success with 95% confidence interval</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid stroke="#263b55" vertical={false} />
          <XAxis dataKey="name" {...AXIS} />
          <YAxis domain={[0, 100]} unit="%" {...AXIS} />
          <Tooltip {...TIP} formatter={(v: number) => [`${v.toFixed(0)}%`, "success"]} />
          <Bar dataKey="rate" fill="#3fc1a5" radius={[3, 3, 0, 0]} maxBarSize={70}>
            <ErrorBar dataKey="err" width={10} stroke="#e7eef6" strokeWidth={1.5} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function CostChart<T extends Comparison>({ rows, name }: { rows: T[]; name: (r: T) => string }) {
  const data = rows.map((r) => ({ name: name(r), perRun: r.avg_cost_usd ?? 0, perSuccess: r.cost_per_success_usd ?? 0 }));
  return (
    <div className="chart-box">
      <h3>Cost per run (slate) and per successful run (amber), USD</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid stroke="#263b55" vertical={false} />
          <XAxis dataKey="name" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={(v: number) => v.toFixed(4)} width={64} />
          <Tooltip {...TIP} formatter={(v: number, n: string) => [usd(v), n === "perRun" ? "per run" : "per successful run"]} />
          <Bar dataKey="perRun" fill="#4d6889" radius={[3, 3, 0, 0]} maxBarSize={40} />
          <Bar dataKey="perSuccess" fill="#f0a63a" radius={[3, 3, 0, 0]} maxBarSize={40} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Compare({ agent }: { agent: string }) {
  const models = useData(() => get<ModelRow[]>("models", { agent }), [agent], 15000);
  const [model, setModel] = useState("");
  const prompts = useData(() => get<PromptRow[]>("prompt-versions", { agent, model }), [agent, model], 15000);

  if (models.error) return <Failed error={models.error} />;
  if (!models.data) return <Loading />;
  const shortName = (m: ModelRow) => m.model.split("/").pop() ?? m.model;
  const mv = verdict(models.data, shortName);
  const pv = prompts.data ? verdict(prompts.data, (p: PromptRow) => p.prompt_version) : null;

  return (
    <>
      <h1>Compare</h1>
      <p className="lede">Which model and which prompt make {agent} more reliable, and what each correct answer really costs. Failed runs still cost money, so cost per successful run is the number to optimize.</p>

      <section className="section">
        <h2>Models</h2>
        {models.data.length === 0 ? <div className="empty">No runs with a recorded model yet.</div> : (
          <>
            {mv && <p className="callout">{mv}</p>}
            <div className="table-wrap" style={{ marginTop: 14 }}><table>
              <thead><tr><th>Model</th><th className="num">Runs</th><th>Success</th><th className="num">p50</th><th className="num">p95</th>
                <th className="num">First token</th><th className="num">Tokens/s</th><th className="num">Per run</th><th className="num">Per success</th><th className="num">vs best</th></tr></thead>
              <tbody>{models.data.map((m) => (
                <tr key={m.model} className="click" onClick={() => (location.hash = `/runs?model=${encodeURIComponent(m.model)}`)}>
                  <td>{m.model}</td><td className="num">{m.runs}</td><td><CiBar rate={m.success_rate} ci={m.success_ci95} /></td>
                  <td className="num">{secs(m.p50_latency_ms)}</td><td className="num">{secs(m.p95_latency_ms)}</td>
                  <td className="num">{secs(m.p50_ttft_ms)}</td><td className="num">{num(m.tokens_per_s)}</td>
                  <td className="num">{usd(m.avg_cost_usd)}</td><td className="num"><b>{usd(m.cost_per_success_usd)}</b></td>
                  <td className={`num ${m.p_value_vs_best == null ? "best" : ""}`}>{pval(m.p_value_vs_best)}</td>
                </tr>))}</tbody>
            </table></div>
            <div className="grid2" style={{ marginTop: 18 }}>
              <SuccessChart rows={models.data} name={shortName} />
              <CostChart rows={models.data} name={shortName} />
            </div>
          </>
        )}
      </section>

      <section className="section">
        <h2>Prompt versions</h2>
        <div className="filters">
          <select aria-label="Model for prompt comparison" value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">All models</option>
            {models.data.map((m) => <option key={m.model} value={m.model}>{m.model}</option>)}
          </select>
        </div>
        {prompts.error ? <Failed error={prompts.error} /> : !prompts.data ? <Loading /> : prompts.data.length === 0 ? (
          <div className="empty">No prompt versions recorded for this selection.</div>
        ) : (
          <>
            {pv && <p className="callout">{pv}</p>}
            <div className="table-wrap" style={{ marginTop: 14 }}><table>
              <thead><tr><th>Prompt</th><th className="num">Runs</th><th>Success</th><th className="num">p50</th><th className="num">p95</th>
                <th className="num">Retries</th><th className="num">Tool errors</th><th className="num">Per success</th><th className="num">vs best</th></tr></thead>
              <tbody>{prompts.data.map((p) => (
                <tr key={p.prompt_version} className="click" onClick={() => (location.hash = `/runs?prompt=${p.prompt_version}${model ? `&model=${encodeURIComponent(model)}` : ""}`)}>
                  <td>{p.prompt_version}</td><td className="num">{p.runs}</td><td><CiBar rate={p.success_rate} ci={p.success_ci95} /></td>
                  <td className="num">{secs(p.p50_latency_ms)}</td><td className="num">{secs(p.p95_latency_ms)}</td>
                  <td className="num">{num(p.avg_retries, 2)}</td><td className="num">{num(p.avg_tool_errors, 2)}</td>
                  <td className="num"><b>{usd(p.cost_per_success_usd)}</b></td>
                  <td className={`num ${p.p_value_vs_best == null ? "best" : ""}`}>{pval(p.p_value_vs_best)}</td>
                </tr>))}</tbody>
            </table></div>
          </>
        )}
      </section>
    </>
  );
}
