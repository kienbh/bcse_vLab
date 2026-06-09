"use client";

import {
  Activity,
  Cpu,
  HardDrive,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Thermometer,
  Zap,
} from "lucide-react";

import {
  fmtBytes,
  fmtMb,
  loadTier,
  useVpsMetrics,
  type LoadTier,
  type VpsMetrics,
} from "@/lib/useVpsMetrics";

/** Sidebar dashboard panel — rendered next to a VPS the SV is actively
 *  holding a block on. Shows everything the badge does, plus temperature
 *  and the GPU process list (every user's process, per thầy's call so SVs
 *  can self-coordinate when sharing the box).
 */
export function VpsMetricsSidebar({
  deviceId,
  deviceName,
}: {
  deviceId: string;
  deviceName: string;
}) {
  const { metrics, loading, error, paused, setPaused, refresh } =
    useVpsMetrics(deviceId);

  return (
    <div className="surface flex flex-col gap-3 p-4">
      <header className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-purple-600 dark:text-purple-300">
            Tải VPS — live
          </p>
          <p className="font-mono text-sm font-bold text-slate-800 dark:text-slate-100">
            {deviceName}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setPaused(!paused)}
            title={paused ? "Tiếp tục cập nhật mỗi 30s" : "Tạm dừng polling"}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
          </button>
          <button
            type="button"
            onClick={refresh}
            title="Làm mới ngay"
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <RefreshCw className="h-3 w-3" />
          </button>
        </div>
      </header>

      {loading && !metrics && (
        <div className="flex items-center justify-center gap-2 rounded-md bg-slate-100 px-3 py-6 text-sm text-slate-500 dark:bg-slate-900 dark:text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Đang đo lần đầu...
        </div>
      )}

      {error && !metrics && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
          Không tải được metrics: <span className="font-mono">{error}</span>
        </div>
      )}

      {metrics && <MetricsBody metrics={metrics} />}

      {metrics && (
        <footer className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
          <span>
            Cập nhật{" "}
            {new Date(metrics.fetched_at).toLocaleTimeString("vi-VN", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
            {metrics.cached ? " · cache" : " · live"}
          </span>
          <span>
            {paused ? "Đã tạm dừng" : "Tự refresh 30s"}
          </span>
        </footer>
      )}
    </div>
  );
}

function MetricsBody({ metrics }: { metrics: VpsMetrics }) {
  if (metrics.error || !metrics.gpu) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
        <p className="font-semibold">Không đo được tải</p>
        <p className="mt-1 font-mono text-[10px]">
          {metrics.error ?? "VPS không có GPU hoặc nvidia-smi lỗi"}
        </p>
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
  // Temperature has its own scale — under 60 °C is comfortable, 60-80 warm,
  // above 80 the card is throttling. Map to the same low/mid/high buckets so
  // the bar reuses the badge palette.
  const tempTier: LoadTier =
    gpu.temp_c < 60 ? "low" : gpu.temp_c < 80 ? "mid" : "high";

  return (
    <div className="flex flex-col gap-3">
      {/* GPU + temperature header */}
      <div className="flex items-center justify-between rounded-md border border-purple-200 bg-gradient-to-r from-purple-50 to-fuchsia-50 px-3 py-2 dark:border-purple-800 dark:from-purple-950/40 dark:to-fuchsia-950/40">
        <span className="inline-flex items-center gap-1.5 text-xs font-bold text-purple-800 dark:text-purple-100">
          <Zap className="h-4 w-4" />
          {gpu.name}
        </span>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
            tempTier === "low"
              ? "bg-emerald-200 text-emerald-900 dark:bg-emerald-900/60 dark:text-emerald-100"
              : tempTier === "mid"
                ? "bg-amber-200 text-amber-900 dark:bg-amber-900/60 dark:text-amber-100"
                : "bg-rose-200 text-rose-900 dark:bg-rose-900/60 dark:text-rose-100"
          }`}
        >
          <Thermometer className="h-3 w-3" />
          {gpu.temp_c}°C
        </span>
      </div>

      <Bar
        icon={<Zap className="h-4 w-4" />}
        label="GPU"
        pct={gpu.util_pct}
        right={`${gpu.util_pct}%`}
      />
      <Bar
        icon={<Cpu className="h-4 w-4" />}
        label="VRAM"
        pct={vramPct}
        right={`${fmtMb(gpu.vram_used_mb)} / ${fmtMb(gpu.vram_total_mb)}`}
      />
      {metrics.disk && (
        <Bar
          icon={<HardDrive className="h-4 w-4" />}
          label={`Ổ ${metrics.disk.mount}`}
          pct={diskPct}
          right={`Còn ${fmtBytes(metrics.disk.free_bytes)} / ${fmtBytes(metrics.disk.total_bytes)}`}
        />
      )}

      {/* GPU process list — every user (per thầy's call: SVs share the box,
          they need to see who's pinning the card). Filter is intentional:
          only processes with > 0 MB VRAM, so kernel threads don't clutter. */}
      <div>
        <p className="mb-1.5 flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">
          <Activity className="h-3 w-3" />
          Process đang chiếm GPU
        </p>
        {metrics.processes.length === 0 ? (
          <p className="rounded-md bg-slate-100 px-3 py-2 text-[11px] italic text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            Không có process nào — GPU đang rỗi.
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {metrics.processes.map((p) => (
              <li
                key={p.pid}
                className="flex items-center justify-between rounded-md bg-slate-100 px-2.5 py-1 font-mono text-[11px] text-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                <span className="truncate">
                  <span className="text-slate-400">pid </span>
                  {p.pid}{" "}
                  <span className="text-slate-500 dark:text-slate-400">
                    · {p.name}
                  </span>
                </span>
                <span className="font-semibold text-purple-700 dark:text-purple-300">
                  {fmtMb(p.vram_mb)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Bar({
  icon,
  label,
  pct,
  right,
}: {
  icon: React.ReactNode;
  label: string;
  pct: number;
  right: string;
}) {
  const tier = loadTier(pct);
  const fill = {
    low: "bg-emerald-500",
    mid: "bg-amber-500",
    high: "bg-rose-500",
  }[tier];
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[11px]">
        <span className="inline-flex items-center gap-1 font-semibold text-slate-700 dark:text-slate-200">
          {icon}
          {label}
        </span>
        <span className="font-mono text-slate-500 dark:text-slate-400">{right}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div
          className={`h-full ${fill} transition-all`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}
