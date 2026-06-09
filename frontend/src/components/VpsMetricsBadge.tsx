"use client";

import { Activity, Loader2 } from "lucide-react";

import { fmtBytes, type VpsMetrics } from "@/lib/useVpsMetrics";

/** Live load strip on a GPU-VPS card.
 *
 * Single question the SV is trying to answer: "máy này load được model của em
 * không?" — that's a VRAM question, not a GPU-util question. A model that's
 * already loaded but idle (GPU 0 %, VRAM 47/48) blocks new users even though
 * util says "rỗi", so we tier on **free VRAM** and surface util/temp/processes
 * in the sidebar where someone who's already blocking the box can act on them.
 *
 * Header reads as a sentence ("Còn 42 GB VRAM trống") so a glancing student
 * doesn't need to parse a chip + number into meaning. Two cells below show
 * VRAM and disk used/total with bars — same pattern, same reading direction.
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
      <div className="flex items-center justify-center gap-1.5 rounded-md border border-purple-200 bg-purple-50/50 px-3 py-2 text-xs text-purple-700 dark:border-purple-900/40 dark:bg-purple-950/20 dark:text-purple-300">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Đang đo tải máy...
      </div>
    );
  }
  if (!metrics) return null;

  if (metrics.error || !metrics.gpu || metrics.gpu.vram_total_mb === 0) {
    return (
      <div
        className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200"
        title={
          metrics.error
            ? `Backend không SSH được vào VPS: ${metrics.error}`
            : "VPS không trả nvidia-smi"
        }
      >
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 font-semibold">
            <Activity className="h-3.5 w-3.5" />
            Chưa đo được tải máy
          </span>
          <span className="font-mono text-[10px] opacity-70">
            {metrics.error ?? "no GPU data"}
          </span>
        </div>
      </div>
    );
  }

  const gpu = metrics.gpu;
  const vramUsedGb = gpu.vram_used_mb / 1024;
  const vramTotalGb = gpu.vram_total_mb / 1024;
  const vramFreeGb = vramTotalGb - vramUsedGb;
  const vramUsedPct = Math.round((gpu.vram_used_mb / gpu.vram_total_mb) * 100);

  const diskFree = metrics.disk?.free_bytes ?? 0;
  const diskTotal = metrics.disk?.total_bytes ?? 0;
  const diskUsedPct =
    diskTotal > 0 ? Math.round(((diskTotal - diskFree) / diskTotal) * 100) : 0;

  // Tier on free VRAM, not used%. A 7B model needs ~6 GB, a 13B needs
  // ~10 GB — picking 8 GB as the "comfortable" cutoff aligns with the
  // smallest realistic training/inference workload SVs run.
  const tier: "low" | "mid" | "high" =
    vramFreeGb >= 8 ? "low" : vramFreeGb >= 2 ? "mid" : "high";

  const tone = {
    low: {
      box: "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30",
      dot: "bg-emerald-500",
      header: "text-emerald-800 dark:text-emerald-200",
      bar: "bg-emerald-500",
    },
    mid: {
      box: "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30",
      dot: "bg-amber-500",
      header: "text-amber-800 dark:text-amber-200",
      bar: "bg-amber-500",
    },
    high: {
      box: "border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/30",
      dot: "bg-rose-500",
      header: "text-rose-800 dark:text-rose-200",
      bar: "bg-rose-500",
    },
  }[tier];

  const headerText = {
    low: `Còn ${vramFreeGb.toFixed(0)} GB VRAM trống — sẵn sàng load model`,
    mid: `Còn ${vramFreeGb.toFixed(1)} GB VRAM — chỉ load được model nhỏ`,
    high: `Còn ${vramFreeGb.toFixed(1)} GB VRAM — gần đầy, khó load thêm`,
  }[tier];

  const fmtAt = new Date(metrics.fetched_at).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className={`flex flex-col gap-2 rounded-md border ${tone.box} px-3 py-2`}
      title={`${gpu.name} · GPU ${gpu.util_pct}% · ${gpu.temp_c}°C · cập nhật ${fmtAt} (${metrics.cached ? "cache" : "live"})`}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={`inline-flex items-center gap-1.5 text-[12px] font-bold ${tone.header}`}
        >
          <span className={`h-2 w-2 rounded-full ${tone.dot} shadow`} />
          {headerText}
        </span>
        <span className="font-mono text-[9px] uppercase tracking-wider opacity-60">
          {fmtAt}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Cell
          label="VRAM"
          big={`${vramUsedGb.toFixed(1)} / ${vramTotalGb.toFixed(0)} GB`}
          sub="đã dùng"
          pct={vramUsedPct}
          barColor={tone.bar}
        />
        {metrics.disk && (
          <Cell
            label="Ổ /home"
            big={`${fmtBytes(diskTotal - diskFree)} / ${fmtBytes(diskTotal)}`}
            sub={`còn ${fmtBytes(diskFree)}`}
            pct={diskUsedPct}
            barColor={diskUsedPct >= 80 ? "bg-rose-500" : diskUsedPct >= 50 ? "bg-amber-500" : "bg-emerald-500"}
          />
        )}
      </div>
    </div>
  );
}

function Cell({
  label,
  big,
  sub,
  pct,
  barColor,
}: {
  label: string;
  big: string;
  sub: string;
  pct: number;
  barColor: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-white/60 px-2 py-1.5 dark:bg-slate-900/50">
      <div className="flex items-baseline justify-between gap-1">
        <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">
          {label}
        </span>
        <span className="text-[9px] text-slate-400 dark:text-slate-500">{sub}</span>
      </div>
      <span className="font-mono text-[12px] font-bold text-slate-800 dark:text-slate-100">
        {big}
      </span>
      <div className="h-1 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div
          className={`h-full ${barColor} transition-all`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}
