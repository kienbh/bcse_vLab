"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiGet } from "@/lib/auth";

/** Live VPS-GPU metrics. Backend caches for 25 s; we poll at 30 s. */
export type VpsMetrics = {
  device_id: string;
  fetched_at: string;
  cached: boolean;
  error: string | null;
  gpu: {
    name: string;
    util_pct: number;
    vram_used_mb: number;
    vram_total_mb: number;
    temp_c: number;
  } | null;
  disk: {
    mount: string;
    used_bytes: number;
    total_bytes: number;
    free_bytes: number;
  } | null;
  processes: { pid: number; vram_mb: number; name: string }[];
};

const POLL_INTERVAL_MS = 30_000;

/** Bulk hook for the family-dashboard list view.
 *
 * Pause-on-hidden matters because the dashboard sits in a long-lived tab —
 * we don't want to keep hammering the backend (and through it, SSH on the
 * VPS) while the user has switched to another window for hours.
 */
export function useVpsMetricsBulk(
  tier: string = "gpu",
  opts: { enabled?: boolean } = {},
): {
  byId: Map<string, VpsMetrics>;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const enabled = opts.enabled ?? true;
  const [byId, setById] = useState<Map<string, VpsMetrics>>(new Map());
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false);

  const fetchOnce = useCallback(async () => {
    if (!enabled) return;
    if (inflight.current) return;
    inflight.current = true;
    try {
      const r = await apiGet(`/vps-metrics?tier=${encodeURIComponent(tier)}`);
      if (!r.ok) {
        setError(`HTTP ${r.status}`);
        return;
      }
      const data: { tier: string; metrics: VpsMetrics[] } = await r.json();
      const next = new Map<string, VpsMetrics>();
      for (const m of data.metrics) next.set(m.device_id, m);
      setById(next);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      inflight.current = false;
    }
  }, [tier, enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer != null) return;
      fetchOnce();
      timer = setInterval(() => {
        if (!document.hidden && !cancelled) fetchOnce();
      }, POLL_INTERVAL_MS);
    };
    const stop = () => {
      if (timer != null) {
        clearInterval(timer);
        timer = null;
      }
    };

    const onVisibility = () => {
      if (document.hidden) stop();
      else {
        // Tab is visible again — fetch immediately, then resume polling.
        // Skipping the immediate fetch leaves stale numbers on screen for
        // up to 30 s, which defeats the whole point of metrics.
        fetchOnce();
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [fetchOnce, enabled]);

  return { byId, loading, error, refresh: fetchOnce };
}

/** Single-device hook for the sidebar panel. Same polling behaviour. */
export function useVpsMetrics(deviceId: string | null): {
  metrics: VpsMetrics | null;
  loading: boolean;
  error: string | null;
  paused: boolean;
  setPaused: (p: boolean) => void;
  refresh: () => void;
} {
  const [metrics, setMetrics] = useState<VpsMetrics | null>(null);
  const [loading, setLoading] = useState(deviceId !== null);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const fetchOnce = useCallback(async () => {
    if (!deviceId) return;
    try {
      const r = await apiGet(`/vps-metrics/${deviceId}`);
      if (!r.ok) {
        setError(`HTTP ${r.status}`);
        return;
      }
      const data: VpsMetrics = await r.json();
      setMetrics(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    if (!deviceId) return;
    let timer: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (timer != null) return;
      fetchOnce();
      timer = setInterval(() => {
        if (!document.hidden && !pausedRef.current) fetchOnce();
      }, POLL_INTERVAL_MS);
    };
    const stop = () => {
      if (timer != null) {
        clearInterval(timer);
        timer = null;
      }
    };

    const onVisibility = () => {
      if (document.hidden) stop();
      else {
        fetchOnce();
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [deviceId, fetchOnce]);

  return { metrics, loading, error, paused, setPaused, refresh: fetchOnce };
}

// ----- Formatters shared by badge + sidebar -------------------------------

export function fmtBytes(b: number): string {
  if (b >= 1024 ** 4) return `${(b / 1024 ** 4).toFixed(1)} TB`;
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(0)} GB`;
  if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(0)} MB`;
  return `${b} B`;
}

export function fmtMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

/** Bucket a percent value into a load tier so badge/bar colours stay in sync. */
export type LoadTier = "low" | "mid" | "high";
export function loadTier(pct: number): LoadTier {
  if (pct < 50) return "low";
  if (pct < 80) return "mid";
  return "high";
}
