"use client";

import { useEffect, useId, useState } from "react";

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
    <div
      className={`surface flex animate-fade-in flex-col gap-4 p-5 transition-shadow ${
        anyNearFull ? "shadow-[0_0_0_1px_rgba(225,29,72,0.25),0_8px_24px_-8px_rgba(225,29,72,0.35)]" : ""
      }`}
    >
      <header className="flex items-center gap-2.5">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-purple-500 to-fuchsia-600 text-white shadow-md shadow-purple-500/30">
          <HardDrive className="h-4.5 w-4.5" />
        </div>
        <div>
          <h2 className="text-sm font-bold text-slate-800 dark:text-slate-100">
            Dung lượng ổ cứng — VPS-GPU
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            3 slot (ai01/ai02/ai03) + ổ đĩa vật lý dùng chung trên máy chủ
          </p>
        </div>
      </header>

      <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-start">
        <PieChart slices={slices} />
        <ul className="flex flex-1 flex-col gap-3">
          {slices.map((s) => {
            const pct = s.totalBytes > 0 ? Math.round((s.usedBytes / s.totalBytes) * 100) : 0;
            const barPct = Math.min(100, pct);
            const overQuota = pct >= OVER_QUOTA_PCT;
            const nearFull = pct >= NEAR_FULL_PCT;
            const dotColor = overQuota ? "#9f1239" : nearFull ? "#e11d48" : s.color;
            return (
              <li key={s.key} className="flex flex-col gap-1">
                <div className="flex items-center gap-2 text-xs">
                  <span
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${nearFull ? "animate-pulse-slow" : ""}`}
                    style={{ backgroundColor: dotColor, boxShadow: nearFull ? `0 0 6px ${dotColor}` : undefined }}
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
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                  <div
                    className="h-full rounded-full transition-[width] duration-1000 ease-out"
                    style={{ width: `${barPct}%`, backgroundColor: dotColor }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {anyNearFull && (
        <div className="flex animate-slide-up items-start gap-2 rounded-md border border-rose-300 bg-rose-50 px-3 py-2.5 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 animate-pulse-slow" />
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
  // Each ring is its own used/remaining arc, stacked as concentric donuts —
  // a single donut mixing differently-scaled slices (per-slot quota vs host
  // disk) would misrepresent proportions, so N stacked rings is the honest
  // shape. No external chart lib: plain SVG + CSS transitions.
  const size = 132;
  const stroke = 11;
  const gap = 4;
  const cx = size / 2;
  const cy = size / 2;
  const gradId = useId();

  // Draw-in-from-zero on mount: render at pct=0 for one frame, then flip to
  // real values so the CSS transition on strokeDashoffset animates the arcs
  // sweeping in. Subsequent prop changes (30 s poll) animate the same way.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // Center label surfaces whichever slice is closest to trouble — the one
  // number worth reading without scanning the legend.
  const worst = slices.reduce((a, b) => {
    const pa = a.totalBytes > 0 ? a.usedBytes / a.totalBytes : 0;
    const pb = b.totalBytes > 0 ? b.usedBytes / b.totalBytes : 0;
    return pb > pa ? b : a;
  }, slices[0]);
  const worstPct = worst.totalBytes > 0 ? Math.round((worst.usedBytes / worst.totalBytes) * 100) : 0;
  const worstOverQuota = worstPct >= OVER_QUOTA_PCT;
  const worstNearFull = worstPct >= NEAR_FULL_PCT;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          {slices.map((s) => (
            <radialGradient key={s.key} id={`${gradId}-${s.key}`} cx="35%" cy="35%" r="75%">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.65} />
              <stop offset="100%" stopColor={s.color} />
            </radialGradient>
          ))}
          <filter id={`${gradId}-glow`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {slices.map((s, i) => {
          const r = size / 2 - stroke / 2 - i * (stroke + gap);
          if (r <= 0) return null;
          const circumference = 2 * Math.PI * r;
          const rawPct = s.totalBytes > 0 ? s.usedBytes / s.totalBytes : 0;
          const pct = Math.min(1, rawPct);
          const offset = mounted ? circumference * (1 - pct) : circumference;
          const overQuota = rawPct * 100 >= OVER_QUOTA_PCT;
          const nearFull = rawPct * 100 >= NEAR_FULL_PCT;
          const strokeColor = overQuota ? "#9f1239" : nearFull ? "#e11d48" : `url(#${gradId}-${s.key})`;
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
                stroke={strokeColor}
                strokeWidth={stroke}
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                strokeLinecap="round"
                filter={nearFull ? `url(#${gradId}-glow)` : undefined}
                className={`transition-[stroke-dashoffset] duration-1000 ease-out ${
                  nearFull ? "animate-pulse-slow" : ""
                }`}
              />
            </g>
          );
        })}
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <div className="flex flex-col items-center justify-center rounded-full bg-white/90 px-1.5 py-1 shadow-sm ring-1 ring-black/5 dark:bg-slate-900/90 dark:ring-white/10">
          <span
            className={`font-mono text-base font-extrabold leading-none ${
              worstOverQuota
                ? "text-rose-700 dark:text-rose-400"
                : worstNearFull
                  ? "text-rose-600 dark:text-rose-400"
                  : "text-slate-700 dark:text-slate-200"
            }`}
          >
            {worstPct}%
          </span>
          <span className="mt-0.5 whitespace-nowrap text-[7px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {worstOverQuota ? "vượt quota" : "cao nhất"}
          </span>
        </div>
      </div>
    </div>
  );
}
