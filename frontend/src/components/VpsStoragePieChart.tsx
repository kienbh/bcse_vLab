"use client";

import { AlertTriangle, HardDrive } from "lucide-react";

import { fmtBytes, type VpsMetrics } from "@/lib/useVpsMetrics";

/** Threshold at which a slice is considered "gần đầy" and turns warning-red. */
const NEAR_FULL_PCT = 80;
/** Threshold at which a slice has exceeded its declared quota entirely —
 *  quota here is a soft/logical limit (not an enforced filesystem quota),
 *  so `du $HOME` can legitimately read past 100 %. */
const OVER_QUOTA_PCT = 100;

type Slice = {
  key: string;
  label: string;
  usedBytes: number;
  totalBytes: number;
  color: string;
};

/**
 * Storage overview for the GPU tier — one slice per slot (ai01/ai02/ai03,
 * each against its 300 GB quota) plus one slice for the physical disk the
 * three slots share on host 192.168.2.98 (against `df` on that host).
 *
 * Per-slot "used" comes from `du $HOME` (metrics.home_used_bytes) — the same
 * ground-truth VpsMetricsBadge uses, so the pie always agrees with the cards
 * above it. The host slice reuses `metrics.disk` (a `df /home` on the shared
 * filesystem — identical across the three slots since they're one machine).
 *
 * No backup/restore exists for this tier (see vps_admin.py — "Reset = mất
 * hết", no snapshot). This chart's only job is to warn early enough that
 * users copy their own data out before that becomes a problem.
 */
export function VpsStoragePieChart({
  devices,
  metricsById,
}: {
  devices: { id: string; name: string; capabilities?: Record<string, unknown> | null }[];
  metricsById: Map<string, VpsMetrics>;
}) {
  const slotColors = ["#a855f7", "#ec4899", "#6366f1"]; // purple / pink / indigo — distinct from warning red/amber

  const slotSlices: (Slice | null)[] = devices.map((d, i) => {
    const m = metricsById.get(d.id);
    const quotaGb = typeof d.capabilities?.disk_gb === "number" ? (d.capabilities.disk_gb as number) : null;
    if (!m || m.home_used_bytes == null || !quotaGb) return null;
    return {
      key: d.id,
      label: d.name,
      usedBytes: m.home_used_bytes,
      totalBytes: quotaGb * 1024 ** 3,
      color: slotColors[i % slotColors.length],
    };
  });

  // Host disk — any one slot's `disk` field reports the same shared filesystem.
  const hostDisk = devices
    .map((d) => metricsById.get(d.id)?.disk)
    .find((d): d is NonNullable<VpsMetrics["disk"]> => d != null && d.total_bytes > 0);
  const hostSlice: Slice | null = hostDisk
    ? {
        key: "__host__",
        label: "Ổ đĩa vật lý (dùng chung)",
        usedBytes: hostDisk.total_bytes - hostDisk.free_bytes,
        totalBytes: hostDisk.total_bytes,
        color: "#0ea5e9",
      }
    : null;

  const slices = [...slotSlices, hostSlice].filter((s): s is Slice => s !== null);

  if (slices.length === 0) return null;

  const anyNearFull = slices.some(
    (s) => s.totalBytes > 0 && (s.usedBytes / s.totalBytes) * 100 >= NEAR_FULL_PCT,
  );
  const anyOverQuota = slices.some(
    (s) => s.totalBytes > 0 && (s.usedBytes / s.totalBytes) * 100 >= OVER_QUOTA_PCT,
  );

  return (
    <div className="surface flex flex-col gap-4 p-5">
      <header className="flex items-center gap-2">
        <HardDrive className="h-5 w-5 text-purple-600 dark:text-purple-300" />
        <div>
          <h2 className="text-sm font-bold text-slate-800 dark:text-slate-100">
            Dung lượng ổ cứng — VPS-GPU
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            3 slot (ai01/ai02/ai03) + ổ đĩa vật lý dùng chung trên máy chủ
          </p>
        </div>
      </header>

      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
        <PieChart slices={slices} />
        <ul className="flex flex-1 flex-col gap-2">
          {slices.map((s) => {
            const pct = s.totalBytes > 0 ? Math.round((s.usedBytes / s.totalBytes) * 100) : 0;
            const overQuota = pct >= OVER_QUOTA_PCT;
            const nearFull = pct >= NEAR_FULL_PCT;
            return (
              <li key={s.key} className="flex items-center gap-2 text-xs">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: overQuota ? "#9f1239" : nearFull ? "#e11d48" : s.color }}
                />
                <span className="min-w-0 flex-1 truncate font-semibold text-slate-700 dark:text-slate-200">
                  {s.label}
                </span>
                <span
                  className={`shrink-0 font-mono ${
                    overQuota
                      ? "font-extrabold text-rose-800 dark:text-rose-300"
                      : nearFull
                        ? "font-bold text-rose-600 dark:text-rose-400"
                        : "text-slate-500 dark:text-slate-400"
                  }`}
                >
                  {fmtBytes(s.usedBytes)} / {fmtBytes(s.totalBytes)} ({pct}%
                  {overQuota ? " — vượt quota" : ""})
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {anyNearFull && (
        <div className="flex items-start gap-2 rounded-md border border-rose-300 bg-rose-50 px-3 py-2.5 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            <span className="font-bold">
              {anyOverQuota
                ? "Ổ cứng đã vượt quota cho phép."
                : `Ổ cứng sắp đầy (≥${NEAR_FULL_PCT}%).`}
            </span>{" "}
            Vui lòng sao lưu / tải dữ liệu quan trọng về máy cá nhân ngay.
            Nếu máy chủ được reset khi ổ cứng đầy hoặc hết block, <span className="font-bold">chúng tôi không chịu trách nhiệm khôi phục lại dữ liệu đã mất</span>.
          </p>
        </div>
      )}
    </div>
  );
}

function PieChart({ slices }: { slices: Slice[] }) {
  // Each slice is drawn as its own used/remaining ring segment via conic-gradient
  // stops, one ring per slice stacked — but a single donut mixing differently-scaled
  // slices (quota vs host disk) misleads, so instead render N small stacked ring
  // arcs isn't right either. Simplest honest representation: one ring per slice,
  // stacked as concentric donuts, size 96px, no external chart lib needed.
  const size = 112;
  const stroke = 14;
  const gap = 4;
  const cx = size / 2;
  const cy = size / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      {slices.map((s, i) => {
        const r = size / 2 - stroke / 2 - i * (stroke + gap);
        if (r <= 0) return null;
        const circumference = 2 * Math.PI * r;
        const rawPct = s.totalBytes > 0 ? s.usedBytes / s.totalBytes : 0;
        const pct = Math.min(1, rawPct);
        const dash = circumference * pct;
        const overQuota = rawPct * 100 >= OVER_QUOTA_PCT;
        const nearFull = rawPct * 100 >= NEAR_FULL_PCT;
        return (
          <g key={s.key} transform={`rotate(-90 ${cx} ${cy})`}>
            <circle
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke="currentColor"
              className="text-slate-200 dark:text-slate-800"
              strokeWidth={stroke}
            />
            <circle
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={overQuota ? "#9f1239" : nearFull ? "#e11d48" : s.color}
              strokeWidth={stroke}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeLinecap="round"
            />
          </g>
        );
      })}
    </svg>
  );
}
