import { useEffect, useState } from "react";

/** Fetch on mount / when deps change; optionally poll. */
export function useData<T>(load: () => Promise<T>, deps: unknown[], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const run = () =>
      load().then((d) => alive && (setData(d), setError(null))).catch((e) => alive && setError(String(e.message ?? e)));
    run();
    const t = pollMs ? setInterval(run, pollMs) : undefined;
    return () => { alive = false; if (t) clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

export function useHash() {
  const [hash, setHash] = useState(() => window.location.hash.slice(1) || "/");
  useEffect(() => {
    const on = () => setHash(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}
