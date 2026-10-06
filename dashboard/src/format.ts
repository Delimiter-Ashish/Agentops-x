export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`);
export const secs = (ms: number | null | undefined) =>
  ms == null ? "–" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
export const usd = (v: number | null | undefined) =>
  v == null ? "–" : v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(5)}` : `$${v.toFixed(3)}`;
export const num = (v: number | null | undefined, digits = 0) =>
  v == null ? "–" : v.toLocaleString(undefined, { maximumFractionDigits: digits });
export const pval = (p: number | null | undefined) => (p == null ? "best" : p < 0.001 ? "p < 0.001" : `p = ${p.toFixed(3)}`);
export const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const datetime = (iso: string) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const short = (id: string) => id.slice(0, 8);
