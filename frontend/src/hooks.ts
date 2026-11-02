import { useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Run an async function whenever `deps` change and expose {data, error, loading}.
 * A "cancelled" flag stops a slow, outdated response from overwriting a newer one
 * (e.g. while someone drags the horizon slider).
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], debounceMs = 0): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    const timer = setTimeout(() => {
      fn()
        .then((data) => !cancelled && setState({ data, error: null, loading: false }))
        .catch((e: unknown) => !cancelled && setState({ data: null, error: e instanceof Error ? e.message : String(e), loading: false }));
    }, debounceMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
