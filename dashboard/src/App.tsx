import { useEffect, useState } from "react";
import { get, type Agent, type Alert } from "./api";
import { useData, useHash } from "./useData";
import Overview from "./pages/Overview";
import Runs from "./pages/Runs";
import RunView from "./pages/RunView";
import Compare from "./pages/Compare";
import Gpu from "./pages/Gpu";
import Alerts from "./pages/Alerts";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/runs", label: "Runs" },
  { href: "/compare", label: "Compare" },
  { href: "/gpu", label: "GPU" },
  { href: "/alerts", label: "Alerts" },
];

export default function App() {
  const hash = useHash();
  const { data: agents } = useData(() => get<Agent[]>("agents"), [], 15000);
  const [agent, setAgent] = useState<string>(() => localStorage.getItem("aopx.agent") ?? "");
  const [alertTick, setAlertTick] = useState(0);
  const { data: openAlerts } = useData(() => (agent ? get<Alert[]>("alerts", { agent }) : Promise.resolve([])), [agent, alertTick], 10000);

  useEffect(() => {
    if (agents?.length && !agents.some((a) => a.agent === agent)) setAgent(agents[0].agent);
  }, [agents, agent]);
  useEffect(() => { if (agent) localStorage.setItem("aopx.agent", agent); }, [agent]);

  const [path, query = ""] = hash.split("?");
  const params = new URLSearchParams(query);
  let page;
  if (!agent) page = agents && agents.length === 0
    ? <div className="empty">No runs recorded yet. Instrument an agent with the SDK, or run <span className="mono">python -m demo.run</span>, and its runs will show up here.</div>
    : <div className="empty">Loading…</div>;
  else if (path.startsWith("/runs/")) page = <RunView id={path.slice(6)} />;
  else if (path === "/runs") page = <Runs agent={agent} params={params} />;
  else if (path === "/compare") page = <Compare agent={agent} />;
  else if (path === "/gpu") page = <Gpu />;
  else if (path === "/alerts") page = <Alerts agent={agent} onChange={() => setAlertTick((t) => t + 1)} />;
  else page = <Overview agent={agent} />;

  const active = path === "/" ? "/" : NAV.find((n) => n.href !== "/" && path.startsWith(n.href))?.href;
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">AgentOps-X <span>observability</span></div>
        <div className="agent-pick">
          <label htmlFor="agent">Agent</label>
          <select id="agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
            {(agents ?? []).map((a) => <option key={a.agent} value={a.agent}>{a.agent} ({a.runs})</option>)}
          </select>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <a key={n.href} href={`#${n.href}`} className={active === n.href ? "on" : ""}>
              {n.label}
              {n.href === "/alerts" && openAlerts && openAlerts.length > 0 && <span className="count" aria-label={`${openAlerts.length} open alerts`}>{openAlerts.length}</span>}
            </a>))}
        </nav>
        <div className="side-foot">Traces, reliability and cost for LangGraph agents.</div>
      </aside>
      <main>{page}</main>
    </div>
  );
}
