"use client";

import { Clock, Activity, AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Quota = {
  hours_used: number;
  weekly_hours_limit: number;
  hours_remaining: number;
  concurrent: number;
  concurrent_limit: number;
  max_advance_days: number;
  max_duration_hours: number;
};

export function QuotaWidget() {
  const [q, setQ] = useState<Quota | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/bookings/quota`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive) {
          setQ(d);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return <div className="surface h-28 animate-pulse" />;
  }
  if (!q) return null;

  const pct = q.weekly_hours_limit > 0
    ? Math.min(100, (q.hours_used / q.weekly_hours_limit) * 100)
    : 0;
  const nearLimit = pct >= 80;
  const overLimit = pct >= 100;

  const barColor = overLimit
    ? "bg-rose-500"
    : nearLimit
      ? "bg-amber-500"
      : "bg-emerald-500";

  return (
    <div className="surface space-y-3 p-5">
      <header className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Clock className="h-4 w-4 text-vju-500" />
          Quota tuần này
        </h3>
        {overLimit && (
          <span className="flex items-center gap-1 text-[11px] font-semibold text-rose-600 dark:text-rose-400">
            <AlertTriangle className="h-3 w-3" />
            Đã hết
          </span>
        )}
      </header>

      <div>
        <div className="mb-1 flex items-baseline justify-between text-sm">
          <span>
            <span className="text-2xl font-bold tabular-nums">{q.hours_used.toFixed(1)}</span>
            <span className="text-slate-500"> / {q.weekly_hours_limit}h</span>
          </span>
          <span className="text-xs text-slate-500">còn {q.hours_remaining.toFixed(1)}h</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className={`h-full rounded-full transition-all ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 pt-1 text-xs">
        <div className="flex flex-col">
          <span className="font-mono text-slate-500">Đang giữ</span>
          <span className="flex items-baseline gap-1">
            <Activity className="h-3 w-3 text-emerald-500" />
            <span className="font-semibold tabular-nums">{q.concurrent}</span>
            <span className="text-slate-400">/ {q.concurrent_limit}</span>
          </span>
        </div>
        <div className="flex flex-col">
          <span className="font-mono text-slate-500">Đặt trước</span>
          <span className="font-semibold tabular-nums">{q.max_advance_days}d</span>
        </div>
        <div className="flex flex-col">
          <span className="font-mono text-slate-500">Mỗi slot</span>
          <span className="font-semibold tabular-nums">≤{q.max_duration_hours}h</span>
        </div>
      </div>
    </div>
  );
}
