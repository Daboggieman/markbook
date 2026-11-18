/**
 * Thin data-loading hook every list/detail page shares.
 * The fetcher is inline at the call site (so openapi-fetch types flow),
 * this hook owns loading/error/data state and refetching.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { problemMessage } from "../api/problem";

export interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useApiQuery<T>(fetcher: () => Promise<T>, deps: unknown[]): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const d = await fetcher();
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) setError(problemMessage(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, reload };
}

/**
 * Unwrap an openapi-fetch result: return `data` or throw the problem body.
 * The thrown value is the RFC 7807 object — problemMessage() renders it.
 */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown }>,
): Promise<T> {
  const { data, error } = await p;
  if (error) throw error;
  if (data === undefined) throw { status: 0, code: "EMPTY", detail: "No response body", title: "Empty response", type: "about:blank" };
  return data;
}
