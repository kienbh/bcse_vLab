"use client";

import { Clock, Zap, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";

type Phase = "before" | "live" | "ending" | "ended";

function pad(n: number): string {
  return String(Math.max(0, Math.floor(n))).padStart(2, "0");
}

function diffParts(ms: number): { d: number; h: number; m: number; s: number } {
  const total = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return { d, h, m, s };
}

/**
 * Live countdown badge for a booking. Updates every second.
 *
 *   - before slot : "Còn 1d 03:24:11 mới mở"      (gray)
 *   - within  5min: "Sắp mở: 04:33"               (amber pulse)
 *   - live        : "Đang chạy · còn 1:23:45"      (emerald)
 *   - ending in 5min : "Sắp kết thúc · còn 03:11"  (rose pulse)
 *   - ended       : "Đã kết thúc"                  (gray)
 */
export function Countdown({ start, end, compact = false }: { start: string; end: string; compact?: boolean }) {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const startTs = new Date(start).getTime();
  const endTs = new Date(end).getTime();
  let phase: Phase;
  let target: number;

  if (now < startTs) {
    phase = now > startTs - 5 * 60_000 ? "before" : "before";
    target = startTs - now;
  } else if (now < endTs) {
    phase = endTs - now < 5 * 60_000 ? "ending" : "live";
    target = endTs - now;
  } else {
    phase = "ended";
    target = 0;
  }

  const { d, h, m, s } = diffParts(target);
  const within5min = phase === "before" && target < 5 * 60_000;

  const cls: Record<Phase, string> = {
    before: within5min
      ? "bg-amber-100 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200 animate-pulse"
      : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    live: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
    ending: "bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200 animate-pulse",
    ended: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-500",
  };

  const icon: Record<Phase, React.ReactNode> = {
    before: <Clock className="h-3 w-3" />,
    live: <Zap className="h-3 w-3" />,
    ending: <Zap className="h-3 w-3" />,
    ended: <CheckCircle2 className="h-3 w-3" />,
  };

  let label: string;
  if (phase === "before") {
    label = d > 0
      ? `Còn ${d}d ${pad(h)}:${pad(m)}:${pad(s)}`
      : within5min
        ? `Sắp mở: ${pad(m)}:${pad(s)}`
        : `Còn ${pad(h)}:${pad(m)}:${pad(s)}`;
  } else if (phase === "live") {
    label = `Đang chạy · ${pad(h)}:${pad(m)}:${pad(s)}`;
  } else if (phase === "ending") {
    label = `Sắp hết · ${pad(m)}:${pad(s)}`;
  } else {
    label = "Đã kết thúc";
  }

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${compact ? "text-[10px]" : "text-xs"} font-mono font-semibold tabular-nums ${cls[phase]}`}>
      {icon[phase]}
      {label}
    </span>
  );
}
