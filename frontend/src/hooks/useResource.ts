/**
 * Small data-fetching hooks.
 *
 * Deliberately minimal rather than pulling in a query library: every page needs
 * the same four states (loading, error, empty, ready) and a way to refetch after
 * a mutation recalculates the backend figures.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { activeAnalysisId } from '../api/client';
import { toApiError } from '../api/errors';

export interface Resource<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/**
 * Run `loader` on mount and whenever `deps` change.
 *
 * Results from a superseded request are discarded, so a fast reload can never
 * be overwritten by a slower in-flight one.
 */
export function useResource<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);

  useEffect(() => {
    const id = ++requestId.current;
    let cancelled = false;
    setLoading(true);
    setError(null);

    loader()
      .then((result) => {
        if (cancelled || id !== requestId.current) return;
        setData(result);
      })
      .catch((err) => {
        if (cancelled || id !== requestId.current) return;
        setError(toApiError(err));
      })
      .finally(() => {
        if (cancelled || id !== requestId.current) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}

/** The current analysis id, or null when the user has not started one. */
export function useAnalysisId(): string | null {
  const [id] = useState<string | null>(() => activeAnalysisId());
  return id;
}

/** Tracks an in-flight mutation so buttons can disable and report failure. */
export function useMutation<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | null> => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (err) {
        setError(toApiError(err));
        return null;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, clearError: () => setError(null) };
}
