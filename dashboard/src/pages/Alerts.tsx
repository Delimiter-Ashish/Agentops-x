import { useState } from "react";
import { get, post, type Alert } from "../api";
import { useData } from "../useData";
import { Failed, Loading } from "../components/bits";
import { datetime, short } from "../format";

export const KIND_LABEL: Record<string, string> = {
  cost_spike: "Cost spike",
  latency_spike: "Slow run",
  runaway_generation: "Runaway generation",
  budget_exceeded: "Budget stopped run",
};

export default function Alerts({ agent, onChange }: { agent: string; onChange: () => void }) {
  const [showAll, setShowAll] = useState(false);
  const [tick, setTick] = useState(0);
  const { data, error } = useData(() => get<Alert[]>("alerts", { agent, include_acknowledged: showAll ? "true" : undefined }),
    [agent, showAll, tick], 10000);
  const [busy, setBusy] = useState(false);

  const ack = async (id: number) => { await post(`alerts/${id}/ack`); setTick((t) => t + 1); onChange(); };
  const rescan = async () => { setBusy(true); try { await post(`alerts/scan?agent=${encodeURIComponent(agent)}`); } finally { setBusy(false); setTick((t) => t + 1); onChange(); } };

  return (
    <>
      <h1>Alerts</h1>
      <p className="lede">Runs and LLM calls far outside their own normal for the same agent and model: at least several times the median and beyond a robust statistical bar, so ordinary noise never shows up here.</p>
      <div className="filters">
        <select aria-label="Which alerts" value={showAll ? "all" : "open"} onChange={(e) => setShowAll(e.target.value === "all")}>
          <option value="open">Open alerts</option>
          <option value="all">Including acknowledged</option>
        </select>
        <button className="btn" onClick={rescan} disabled={busy}>{busy ? "Checking…" : "Recheck all runs"}</button>
      </div>
      {error ? <Failed error={error} /> : !data ? <Loading /> : data.length === 0 ? (
        <div className="empty">No open alerts. Every finished run is checked automatically; use "Recheck all runs" after importing older data.</div>
      ) : (
        <div className="table-wrap"><table>
          <thead><tr><th>Severity</th><th>What happened</th><th>Details</th><th>Run</th><th>When</th><th /></tr></thead>
          <tbody>{data.map((a) => (
            <tr key={a.id} style={{ opacity: a.acknowledged ? 0.55 : 1 }}>
              <td><span className="status"><span className={`dot ${a.severity === "critical" ? "error" : "failure"}`} />{a.severity === "critical" ? "Critical" : "Warning"}</span></td>
              <td>{KIND_LABEL[a.kind] ?? a.kind}</td>
              <td className="wrap" style={{ color: "var(--ink)" }}>{a.message}</td>
              <td className="mono">{a.run_id ? <a href={`#/runs/${a.run_id}`}>{short(a.run_id)}</a> : "–"}</td>
              <td>{datetime(a.created_at)}</td>
              <td>{!a.acknowledged && <button className="btn quiet" onClick={() => ack(a.id)}>Acknowledge</button>}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </>
  );
}
