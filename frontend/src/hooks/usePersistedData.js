import { useState, useEffect, useCallback } from 'react';
import { getCache, setCache } from '../store';

/**
 * Like useState but backed by the in-memory cache.
 * Data survives page-switches; only re-fetches when stale (>ttlMs).
 */
export function usePersistedData(cacheKey, fetchFn, { ttlMs = 60_000, deps = [] } = {}) {
  const [data, setData] = useState(() => getCache(cacheKey)?.data ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (force = false) => {
    const cached = getCache(cacheKey);
    if (!force && cached && Date.now() - cached.ts < ttlMs) {
      setData(cached.data);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await fetchFn();
      setCache(cacheKey, { data: result, ts: Date.now() });
      setData(result);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [cacheKey, fetchFn, ttlMs]);

  useEffect(() => { load(); }, [load, ...deps]); // eslint-disable-line

  const refresh = () => load(true);
  return { data, loading, error, refresh };
}
