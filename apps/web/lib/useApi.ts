"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export type Remote<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };
type State<T> = { path: string | null; data: T | null; error: string | null; loading: boolean };

/** Fetches `path` (null = nothing to fetch). Data is only ever exposed for the path it was fetched for, so a changed
 *  path can never render the previous path's payload under the wrong type. */
export function useApi<T>(path: string | null): Remote<T> {
  const [state, setState] = useState<State<T>>({ path: null, data: null, error: null, loading: path !== null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let live = true;
    api<T>(path)
      .then((data) => live && setState({ path, data, error: null, loading: false }))
      .catch((e: unknown) => live && setState({ path, data: null, error: e instanceof Error ? e.message : "Request failed", loading: false }));
    return () => { live = false; };
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  if (path === null) return { data: null, error: null, loading: false, reload };
  if (state.path !== path) return { data: null, error: null, loading: true, reload };
  return { data: state.data, error: state.error, loading: state.loading, reload };
}
