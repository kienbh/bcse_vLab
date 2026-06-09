"use client";

import { Activity, HardDrive, Loader2, Zap } from "lucide-react";

import {
  fmtBytes,
  fmtMb,
  loadTier,
  type VpsMetrics,
} from "@/lib/useVpsMetrics";

/** Inline status strip rendered inside the GPU-tier DeviceCard.
 *
 * Three signals — GPU util, VRAM, free disk — colour-coded to the highest
 * load among them so the worst signal wins (a 95 % GPU on a half-full disk
 * is still "hot"). Helps SVs eyeball "máy nào trống nhất" before booking.
 */
export function VpsMetricsBadge({
  metrics,
  loading,
}: {
  metrics: VpsMetrics | null | undefined;
  loading: boolean;
}) {
  if (loading && !metrics) {
    return (
      <div className="flex items-center justify-center gap-1.5 rounded-md border border-purple-200 bg-purple-50/50 px-3 py-1.5 text-[11px] text-purple-700 dark:border-purple-900/40 dark:bg-purple-950/20 dark:text-purple-300">
        <Loader2 className="h-3 w-3 animate-spin" />
        Đang đo tải...
      </div>
    );
  }
  if (!metrics) return null;

  if (metrics.error || !metrics.gpu) {
    return (
      <div
        className="flex items-center justify-between rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200"
        title={
          metrics.error
            ? `Backend không SSH được vào VPS: ${metrics.error}`
            : "VPS không trả nvidia-smi"
        }
      >
        <span className="inline-flex items-center gap-1.5">
          <Activity className="h-3 w-3" />
          Không đo được tải
        </span>
        <span className="font-mono text-[10px] opacity-70">
          {metrics.error ?? "no GPU"}
        </span>
      </div>
    );
  }

  const gpu = metrics.gpu;
  const vramPct = gpu.vram_total_mb > 0
    ? Math.round((gpu.vram_used_mb / gpu.vram_total_mb) * 100)
    : 0;
  const diskPct = metrics.disk && metrics.disk.total_bytes > 0
    ? Math.round(
        ((metrics.disk.total_bytes - metrics.disk.free_bytes) /
          metrics.disk.total_bytes) *
          100,
      )
    : 0;
  // The "worst" of the three drives the colour. A green badge should mean
  // genuinely free — if any signal is hot, the card should warn.
  const worst = Math.max(gpu.util_pct, vramPct, diskPct);
  const tier = loadTier(worst);

  const tone = {
    low: {
      box: "border-emerald-200 bg-emerald-50/80 dark:border-emerald-900/40 dark:bg-emerald-950/30",
      dot: "bg-emerald-500",
      text: "text-emerald-800 dark:text-emerald-200",
    },
    mid: {
      box: "border-amber-200 bg-amber-50/80 dark:border-amber-900/40 dark:bg-amber-950/30",
      dot: "bg-amber-500",
      text: "text-amber-800 dark:text-amber-200",
    },
    high: {
      box: "border-rose-200 bg-rose-50/80 dark:border-rose-900/40 dark:bg-rose-950/30",
      dot: "bg-rose-500",
      text: "text-rose-800 dark:text-rose-200",
    },
  }[tier];

  return (
    <div
      className={`flex items-center justify-between gap-2 rounded-md border ${tone.box} px-3 py-1.5 text-[11px] ${tone.text}`}
      title={`Cập nhật ${new Date(metrics.fetched_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} · ${metrics.cached ? "cache" : "live"} · ${gpu.name}`}
    >
      <span className="inline-flex items-center gap-1.5 font-semibold">
        <span className={`h-2 w-2 rounded-full ${tone.dot} shadow`} />
        Tải hiện tại
      </span>
      <span className="flex items-center gap-2.5 font-mono">
        <span className="inline-flex items-center gap-0.5" title="GPU utilisation">
          <Zap className="h-3 w-3" />
          {gpu.util_pct}%
        </span>
        <span className="inline-flex items-center gap-0.5" title="VRAM used / total">
          <span className="text-[9px] font-bold uppercase tracking-wider opacity-70">vram</span>
          {fmtMb(gpu.vram_used_mb)}/{fmtMb(gpu.vram_total_mb)}
        </span>
        {metrics.disk && (
          <span
            className="inline-flex items-center gap-0.5"
            title={`Ổ ${metrics.disk.mount} còn ${fmtBytes(metrics.disk.free_bytes)}`}
          >
            <HardDrive className="h-3 w-3" />
            {fmtBytes(metrics.disk.free_bytes)}
          </span>
        )}
      </span>
    </div>
  );
}
