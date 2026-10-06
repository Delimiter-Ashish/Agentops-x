import { get, type ModelRow, type PromptRow, type RunRow } from "../api";
import { useData } from "../useData";
import { Failed, Loading, StatusDot } from "../components/bits";
import { datetime, num, secs, short, usd } from "../format";

export default function Runs({ agent, params }: { agent: string; params: URLSearchParams }) {
  const status = params.get("status") ?? "";
  const prompt = params.get("prompt") ?? "";
  const model = params.get("model") ?? "";
  const runs = useData(() => get<RunRow[]>("runs", { agent, status, prompt_version: prompt, model, limit: 200 }),
    [agent, status, prompt, model], 8000);
  const prompts = useData(() => get<PromptRow[]>("prompt-versions", { agent }), [agent]);
  const models = useData(() => get<ModelRow[]>("models", { agent }), [agent]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    location.hash = `/runs${next.toString() ? `?${next}` : ""}`;
  };

  return (
    <>
      <h1>Runs</h1>
      <p className="lede">Every execution of {agent}, newest first. Open a run to see its full trace.</p>
      <div className="filters">
        <select aria-label="Outcome" value={status} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">All outcomes</option>
          <option value="success">Success</option>
          <option value="failure">Wrong answer</option>
          <option value="error">Crashed</option>
          <option value="running">Running</option>
        </select>
        <select aria-label="Prompt version" value={prompt} onChange={(e) => setFilter("prompt", e.target.value)}>
          <option value="">All prompt versions</option>
          {(prompts.data ?? []).map((p) => <option key={p.prompt_version} value={p.prompt_version}>{p.prompt_version}</option>)}
        </select>
        <select aria-label="Model" value={model} onChange={(e) => setFilter("model", e.target.value)}>
          <option value="">All models</option>
          {(models.data ?? []).map((m) => <option key={m.model} value={m.model}>{m.model}</option>)}
        </select>
      </div>

      {runs.error ? <Failed error={runs.error} /> : !runs.data ? <Loading /> : runs.data.length === 0 ? (
        <div className="empty">No runs match these filters.</div>
      ) : (
        <div className="table-wrap"><table>
          <thead><tr>
            <th>Run</th><th>Started</th><th>Outcome</th><th>Prompt</th><th>Model</th>
            <th className="num">Duration</th><th className="num">LLM / tools</th><th className="num">Retries</th>
            <th className="num">Tokens</th><th className="num">Cost</th><th>Why it failed</th>
          </tr></thead>
          <tbody>{runs.data.map((r) => (
            <tr key={r.id} className="click" onClick={() => (location.hash = `/runs/${r.id}`)}>
              <td className="mono"><a href={`#/runs/${r.id}`} onClick={(e) => e.stopPropagation()}>{short(r.id)}</a></td>
              <td>{datetime(r.started_at)}</td>
              <td><StatusDot status={r.status} label={{ success: "Success", failure: "Wrong answer", error: "Crashed", running: "Running" }[r.status]} /></td>
              <td>{r.prompt_version ?? "–"}</td>
              <td className="muted">{r.model ?? "–"}</td>
              <td className="num">{secs(r.latency_ms)}</td>
              <td className="num">{r.llm_calls} / {r.tool_calls}{r.tool_errors ? <span style={{ color: "var(--err)" }}> ({r.tool_errors} err)</span> : null}</td>
              <td className="num" style={{ color: r.retries ? "var(--warn)" : undefined }}>{r.retries}</td>
              <td className="num">{num(r.prompt_tokens + r.completion_tokens)}</td>
              <td className="num">{usd(r.cost_usd)}</td>
              <td className="wrap">{r.failure_reason ?? ""}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </>
  );
}
