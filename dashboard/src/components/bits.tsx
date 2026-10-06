import type { ReactNode } from "react";

export function StatusDot({ status, label }: { status: string; label?: string }) {
  return <span className="status"><span className={`dot ${status}`} />{label ?? status}</span>;
}

export function Kpi({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return <div className="kpi"><div className="k">{label}</div><div className="v">{value}</div>{sub && <div className="s">{sub}</div>}</div>;
}

/** Success rate with its 95% confidence interval drawn as a range. */
export function CiBar({ rate, ci }: { rate: number | null; ci: [number | null, number | null] }) {
  if (rate == null) return <span className="muted">–</span>;
  const [lo, hi] = ci;
  return (
    <span title={`95% CI ${pctStr(lo)} to ${pctStr(hi)}`}>
      <span className="ci">
        {lo != null && hi != null && <span className="range" style={{ left: `${lo * 100}%`, width: `${(hi - lo) * 100}%` }} />}
        <span className="mark" style={{ left: `calc(${rate * 100}% - 1px)` }} />
      </span>
      {pctStr(rate)} <span className="muted">({pctStr(lo)}–{pctStr(hi)})</span>
    </span>
  );
}
const pctStr = (v: number | null) => (v == null ? "–" : `${Math.round(v * 100)}%`);

export function Loading() { return <div className="empty">Loading…</div>; }
export function Failed({ error }: { error: string }) {
  return <div className="error-box">Could not load data: {error}. Check that the API server is running.</div>;
}
