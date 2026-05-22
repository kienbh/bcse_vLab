"use client";

import Link from "next/link";
import { Calendar, Plus, Cpu, Inbox, ExternalLink, X, List, CalendarDays } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { Countdown } from "@/components/Countdown";
import { L, useLocaleListener } from "@/components/LocaleText";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Booking = {
  id: string;
  device_id: string;
  granted_via: string;
  start_time: string;
  end_time: string;
  status: "scheduled" | "active" | "completed" | "cancelled" | "no_show";
  notes: string | null;
};

type Device = { id: string; name: string; model: string; device_type: string };

const STATUS_BADGE: Record<Booking["status"], string> = {
  scheduled: "bg-vju-100 text-vju-700 dark:bg-vju-900/40 dark:text-vju-100",
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  completed: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  cancelled: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  no_show: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
};

const STATUS_BG: Record<Booking["status"], string> = {
  scheduled: "bg-vju-500/30 border-vju-500",
  active: "bg-emerald-500/40 border-emerald-500",
  completed: "bg-slate-400/30 border-slate-400",
  cancelled: "bg-rose-500/20 border-rose-500 opacity-50 line-through",
  no_show: "bg-amber-500/20 border-amber-500 opacity-60",
};

function startOfWeek(d: Date): Date {
  const out = new Date(d);
  const day = out.getDay() || 7;
  out.setHours(0, 0, 0, 0);
  out.setDate(out.getDate() - day + 1);
  return out;
}

function BookingsInner() {
  const locale = useLocaleListener();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [devices, setDevices] = useState<Map<string, Device>>(new Map());
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"list" | "week">("list");
  const [weekOffset, setWeekOffset] = useState(0);
  const [hideOld, setHideOld] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const v = localStorage.getItem("bookings_view");
      if (v === "list" || v === "week") setView(v);
    }
  }, []);
  useEffect(() => {
    if (typeof window !== "undefined") localStorage.setItem("bookings_view", view);
  }, [view]);

  const refresh = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/bookings`, { credentials: "include" }).then((r) => (r.ok ? r.json() : [])),
      fetch(`${API}/devices`, { credentials: "include" }).then((r) => (r.ok ? r.json() : [])),
    ]).then(([b, d]: [Booking[], Device[]]) => {
      setBookings(b);
      setDevices(new Map(d.map((x) => [x.id, x])));
      setLoading(false);
    });
  };
  useEffect(refresh, []);

  const cancel = async (id: string) => {
    if (!confirm("Huỷ booking này?")) return;
    const r = await fetch(`${API}/bookings/${id}/cancel`, { method: "POST", credentials: "include" });
    if (r.ok) refresh();
  };

  const connect = async (id: string) => {
    const r = await fetch(`${API}/sessions/provision/${id}`, { method: "POST", credentials: "include" });
    if (r.ok) {
      const data = await r.json();
      try { await navigator.clipboard?.writeText(data.private_key); } catch { /* */ }
      window.open(data.wetty_url, "_blank");
      return;
    }
    const e = await r.json().catch(() => ({}));
    const code = e?.detail?.code ?? "ERROR";
    if (code === "SESSION_EXISTS") {
      // Already provisioned — re-open the existing web terminal.
      const r2 = await fetch(`${API}/sessions/by-booking/${id}`, { credentials: "include" });
      if (r2.ok) {
        window.open((await r2.json()).wetty_url, "_blank");
        return;
      }
    }
    alert(`Không mở được session: ${code}`);
  };

  const fmt = (iso: string) =>
    new Date(iso).toLocaleString(locale === "vi" ? "vi-VN" : "en-GB", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });

  // Week-view data: 7 days × hours, place each booking as a vertical block
  const weekStart = useMemo(() => {
    const w = startOfWeek(new Date());
    w.setDate(w.getDate() + weekOffset * 7);
    return w;
  }, [weekOffset]);
  const weekEnd = useMemo(() => {
    const w = new Date(weekStart);
    w.setDate(w.getDate() + 7);
    return w;
  }, [weekStart]);

  const visibleBookings = useMemo(() => {
    return bookings.filter((b) => {
      const s = new Date(b.start_time).getTime();
      return s >= weekStart.getTime() && s < weekEnd.getTime();
    });
  }, [bookings, weekStart, weekEnd]);

  // "Clear history" = hide finished/cancelled rows from the list (non-destructive).
  const DONE_STATUSES = new Set(["completed", "cancelled", "no_show"]);
  const listBookings = hideOld
    ? bookings.filter((b) => !DONE_STATUSES.has(b.status))
    : bookings;
  const oldCount = bookings.filter((b) => DONE_STATUSES.has(b.status)).length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            <L k="page.bookings.title" />
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {loading ? "Loading..." : `${bookings.length} lịch`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {oldCount > 0 && (
            <button
              type="button"
              onClick={() => setHideOld((v) => !v)}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              {hideOld
                ? locale === "vi" ? `Hiện lịch sử (${oldCount})` : `Show history (${oldCount})`
                : locale === "vi" ? `Ẩn lịch sử (${oldCount})` : `Hide history (${oldCount})`}
            </button>
          )}
          <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 dark:border-slate-700 dark:bg-slate-900">
            <button
              type="button"
              onClick={() => setView("list")}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold transition ${view === "list" ? "bg-vju-500 text-white" : "text-slate-600 dark:text-slate-300"}`}
            >
              <List className="h-3 w-3" />
              List
            </button>
            <button
              type="button"
              onClick={() => setView("week")}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold transition ${view === "week" ? "bg-vju-500 text-white" : "text-slate-600 dark:text-slate-300"}`}
            >
              <CalendarDays className="h-3 w-3" />
              Tuần
            </button>
          </div>
          <Link
            href="/devices"
            className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-vju-600"
          >
            <Plus className="h-4 w-4" />
            {locale === "vi" ? "Đặt thêm" : "Book new"}
          </Link>
        </div>
      </header>

      {loading ? (
        <div className="surface h-40 animate-pulse" />
      ) : view === "list" ? (
        listBookings.length === 0 ? (
          <div className="surface flex flex-col items-center justify-center gap-3 p-12 text-center">
            <Inbox className="h-10 w-10 text-slate-300" />
            <h2 className="text-base font-semibold">
              <L k="page.bookings.empty.title" />
            </h2>
            <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">
              <L k="page.bookings.empty.desc" />
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {listBookings.map((b) => {
              const d = devices.get(b.device_id);
              const now = Date.now();
              const start = new Date(b.start_time).getTime();
              const end = new Date(b.end_time).getTime();
              const canConnect = (b.status === "scheduled" || b.status === "active") && now >= start - 5 * 60_000 && now < end;
              const canCancel = b.status === "scheduled" || b.status === "active";
              return (
                <li key={b.id} className="surface flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
                  <div className="flex items-center gap-4">
                    <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-vju-500 to-vju-700 text-white shadow-sm">
                      <Cpu className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-mono text-xs uppercase text-slate-500">{d?.name ?? b.device_id}</p>
                      <p className="text-base font-semibold">{d?.model ?? "—"}</p>
                      <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                        <Calendar className="h-3 w-3" />
                        {fmt(b.start_time)} → {new Date(b.end_time).toLocaleTimeString(locale === "vi" ? "vi-VN" : "en-GB", { hour: "2-digit", minute: "2-digit" })}
                      </p>
                      <p className="text-xs italic text-slate-400">via {b.granted_via}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Countdown start={b.start_time} end={b.end_time} />
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${STATUS_BADGE[b.status]}`}>
                      {b.status}
                    </span>
                    {canConnect && (
                      <button
                        type="button"
                        onClick={() => connect(b.id)}
                        className="inline-flex items-center gap-1 rounded-md bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Connect
                      </button>
                    )}
                    {canCancel && (
                      <button
                        type="button"
                        onClick={() => cancel(b.id)}
                        className="inline-flex items-center gap-1 rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-700 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
                      >
                        <X className="h-3 w-3" />
                        Cancel
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )
      ) : (
        <WeekView
          weekStart={weekStart}
          bookings={visibleBookings}
          devices={devices}
          onBack={() => setWeekOffset((w) => w - 1)}
          onForward={() => setWeekOffset((w) => w + 1)}
          onToday={() => setWeekOffset(0)}
          weekOffset={weekOffset}
        />
      )}
    </div>
  );
}

function WeekView({
  weekStart,
  bookings,
  devices,
  onBack,
  onForward,
  onToday,
  weekOffset,
}: {
  weekStart: Date;
  bookings: Booking[];
  devices: Map<string, Device>;
  onBack: () => void;
  onForward: () => void;
  onToday: () => void;
  weekOffset: number;
}) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return d;
  });
  const HOUR_PX = 38; // height of one hour row
  const START_HOUR = 7;
  const END_HOUR = 23;
  const totalRows = END_HOUR - START_HOUR;

  const dayLabel = (d: Date) =>
    d.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" });
  const todayKey = new Date().toDateString();

  return (
    <div className="surface overflow-hidden">
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="text-sm font-semibold">
          {weekStart.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })} —{" "}
          {new Date(weekStart.getTime() + 6 * 86400_000).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}
        </div>
        <div className="inline-flex rounded-md border border-slate-300 bg-white text-xs dark:border-slate-700 dark:bg-slate-900">
          <button onClick={onBack} className="px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800">←</button>
          <button onClick={onToday} className={`px-3 py-1 font-semibold ${weekOffset === 0 ? "bg-vju-500 text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>Tuần này</button>
          <button onClick={onForward} className="px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800">→</button>
        </div>
      </header>

      <div className="grid" style={{ gridTemplateColumns: "60px repeat(7, 1fr)" }}>
        {/* header row */}
        <div className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50" />
        {days.map((d, i) => (
          <div
            key={i}
            className={`border-b border-l border-slate-200 px-2 py-2 text-center text-xs font-semibold dark:border-slate-800 ${
              d.toDateString() === todayKey ? "bg-vju-50 text-vju-700 dark:bg-vju-900/30 dark:text-vju-100" : "bg-slate-50 text-slate-700 dark:bg-slate-800/50 dark:text-slate-300"
            }`}
          >
            {dayLabel(d)}
          </div>
        ))}

        {/* time labels */}
        <div className="bg-slate-50/50 dark:bg-slate-900/30">
          {Array.from({ length: totalRows }, (_, i) => (
            <div
              key={i}
              className="border-b border-slate-200 pr-2 pt-1 text-right font-mono text-[10px] text-slate-400 dark:border-slate-800"
              style={{ height: HOUR_PX }}
            >
              {String(START_HOUR + i).padStart(2, "0")}:00
            </div>
          ))}
        </div>

        {/* day columns with relative-positioned bookings */}
        {days.map((day, di) => {
          const dayStart = new Date(day);
          dayStart.setHours(0, 0, 0, 0);
          const dayBookings = bookings.filter((b) => {
            const bs = new Date(b.start_time);
            return bs.toDateString() === day.toDateString();
          });
          return (
            <div
              key={di}
              className="relative border-l border-slate-200 dark:border-slate-800"
              style={{ height: HOUR_PX * totalRows }}
            >
              {Array.from({ length: totalRows }, (_, i) => (
                <div
                  key={i}
                  className="border-b border-slate-100 dark:border-slate-800/60"
                  style={{ height: HOUR_PX }}
                />
              ))}
              {dayBookings.map((b) => {
                const s = new Date(b.start_time);
                const e = new Date(b.end_time);
                const startMin = (s.getHours() - START_HOUR) * 60 + s.getMinutes();
                const durMin = (e.getTime() - s.getTime()) / 60000;
                if (startMin < 0 || startMin >= totalRows * 60) return null;
                const top = (startMin / 60) * HOUR_PX;
                const height = Math.max(20, (durMin / 60) * HOUR_PX);
                const dev = devices.get(b.device_id);
                return (
                  <div
                    key={b.id}
                    className={`absolute inset-x-1 rounded-md border px-1.5 py-1 text-[10px] shadow-sm ${STATUS_BG[b.status]}`}
                    style={{ top, height }}
                    title={`${dev?.name ?? b.device_id} ${s.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}-${e.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`}
                  >
                    <p className="truncate font-mono font-bold">{dev?.name ?? "?"}</p>
                    <p className="truncate text-[9px] opacity-80">
                      {s.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}-
                      {e.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <p className="border-t border-slate-200 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-800">
        ⓘ Click vào danh sách để cancel/connect. Hiển thị 07:00–23:00. Booking ngoài khung giờ này không hiện trên grid.
      </p>
    </div>
  );
}

export default function BookingsPage() {
  return (
    <AuthGate>
      <BookingsInner />
    </AuthGate>
  );
}
