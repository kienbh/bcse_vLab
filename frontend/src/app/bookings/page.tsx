"use client";

import Link from "next/link";
import {
  Calendar,
  Plus,
  Cpu,
  Inbox,
  ExternalLink,
  X,
  List,
  CalendarDays,
  Power,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { BookingModal } from "@/components/BookingModal";
import type { Device } from "@/components/DeviceCard";
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

type BusySlot = {
  start: string;
  end: string;
  is_mine: boolean;
  booking_id: string;
  status: "scheduled" | "active";
  display: string;
};

type Availability = {
  device_id: string;
  device_name: string;
  from: string;
  to: string;
  busy: BusySlot[];
};

const STATUS_BADGE: Record<Booking["status"], string> = {
  scheduled: "bg-vju-100 text-vju-700 dark:bg-vju-900/40 dark:text-vju-100",
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  completed: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  cancelled: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  no_show: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
};

function startOfWeek(d: Date): Date {
  const out = new Date(d);
  const day = out.getDay() || 7;
  out.setHours(0, 0, 0, 0);
  out.setDate(out.getDate() - day + 1);
  return out;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function BookingsInner() {
  const locale = useLocaleListener();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [devices, setDevices] = useState<Map<string, Device>>(new Map());
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"list" | "week">("list");
  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [bookingOpen, setBookingOpen] = useState<{
    device: Device;
    start?: string;
    end?: string;
  } | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const v = localStorage.getItem("bookings_view");
      if (v === "list" || v === "week") setView(v);
      const dev = localStorage.getItem("bookings_selected_device");
      if (dev) setSelectedDeviceId(dev);
    }
  }, []);
  useEffect(() => {
    if (typeof window !== "undefined") localStorage.setItem("bookings_view", view);
  }, [view]);
  useEffect(() => {
    if (typeof window !== "undefined" && selectedDeviceId) {
      localStorage.setItem("bookings_selected_device", selectedDeviceId);
    }
  }, [selectedDeviceId]);

  const refresh = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/bookings`, { credentials: "include" }).then((r) => (r.ok ? r.json() : [])),
      fetch(`${API}/devices`, { credentials: "include" }).then((r) => (r.ok ? r.json() : [])),
    ]).then(([b, d]: [Booking[], Device[]]) => {
      setBookings(b);
      setDevices(new Map(d.map((x) => [x.id, x])));
      // Default to first device if none selected
      if (!selectedDeviceId && d.length > 0) {
        setSelectedDeviceId(d[0].id);
      }
      setLoading(false);
    });
  }, [selectedDeviceId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    } else {
      const e = await r.json().catch(() => ({}));
      alert(`Không mở được session: ${JSON.stringify(e)}`);
    }
  };

  const fmt = (iso: string) =>
    new Date(iso).toLocaleString(locale === "vi" ? "vi-VN" : "en-GB", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });

  const selectedDevice = selectedDeviceId ? devices.get(selectedDeviceId) ?? null : null;

  const openBookingFromCell = (cellDate: Date) => {
    if (!selectedDevice) return;
    const end = new Date(cellDate);
    end.setHours(end.getHours() + 2);
    setBookingOpen({
      device: selectedDevice,
      start: toLocalInput(cellDate),
      end: toLocalInput(end),
    });
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            <L k="page.bookings.title" />
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {loading ? "Loading..." : `${bookings.length} lịch của bạn`}
          </p>
        </div>
        <div className="flex items-center gap-2">
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
        bookings.length === 0 ? (
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
            {bookings.map((b) => {
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
        <WeekCalendar
          devices={[...devices.values()]}
          selectedDeviceId={selectedDeviceId}
          onSelectDevice={setSelectedDeviceId}
          weekOffset={weekOffset}
          onWeekChange={setWeekOffset}
          onEmptyCellClick={openBookingFromCell}
          onCancel={(id) => cancel(id).then(refresh)}
          onConnect={connect}
        />
      )}

      {bookingOpen && (
        <BookingModal
          device={bookingOpen.device}
          initialStart={bookingOpen.start}
          initialEnd={bookingOpen.end}
          onClose={() => setBookingOpen(null)}
          onBooked={() => {
            setBookingOpen(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

const HOUR_PX = 40;
const START_HOUR = 7;
const END_HOUR = 23;
const TOTAL_ROWS = END_HOUR - START_HOUR;

function WeekCalendar({
  devices,
  selectedDeviceId,
  onSelectDevice,
  weekOffset,
  onWeekChange,
  onEmptyCellClick,
  onCancel,
  onConnect,
}: {
  devices: Device[];
  selectedDeviceId: string | null;
  onSelectDevice: (id: string) => void;
  weekOffset: number;
  onWeekChange: (offset: number) => void;
  onEmptyCellClick: (cellDate: Date) => void;
  onCancel: (bookingId: string) => void;
  onConnect: (bookingId: string) => void;
}) {
  const [data, setData] = useState<Availability | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedBookingId, setExpandedBookingId] = useState<string | null>(null);

  const weekStart = useMemo(() => {
    const w = startOfWeek(new Date());
    w.setDate(w.getDate() + weekOffset * 7);
    return w;
  }, [weekOffset]);

  const weekEnd = useMemo(() => {
    const e = new Date(weekStart);
    e.setDate(e.getDate() + 7);
    return e;
  }, [weekStart]);

  useEffect(() => {
    if (!selectedDeviceId) return;
    setLoading(true);
    setError(null);
    const isoWeekStart = weekStart.toISOString();
    fetch(
      `${API}/devices/${selectedDeviceId}/availability?week_start=${encodeURIComponent(isoWeekStart)}`,
      { credentials: "include" },
    )
      .then(async (r) => {
        if (r.ok) {
          setData(await r.json());
        } else {
          const e = await r.json().catch(() => ({}));
          setError(e?.detail?.code === "ACCESS_DENIED"
            ? "Bạn chưa được cấp quyền xem lịch thiết bị này."
            : `Lỗi tải lịch: ${e?.detail?.code ?? r.status}`);
          setData(null);
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [selectedDeviceId, weekStart]);

  const days = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [weekStart]);

  const dayLabel = (d: Date) =>
    d.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" });
  const todayKey = new Date().toDateString();

  const selectedDevice = devices.find((d) => d.id === selectedDeviceId);

  return (
    <div className="surface overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <Cpu className="h-4 w-4 text-vju-500" />
          <select
            value={selectedDeviceId ?? ""}
            onChange={(e) => onSelectDevice(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="" disabled>Chọn thiết bị...</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>{d.name} — {d.model}</option>
            ))}
          </select>
          <span className="text-xs text-slate-500">
            {weekStart.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })} —{" "}
            {new Date(weekEnd.getTime() - 1).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}
          </span>
        </div>
        <div className="inline-flex rounded-md border border-slate-300 bg-white text-xs dark:border-slate-700 dark:bg-slate-900">
          <button onClick={() => onWeekChange(weekOffset - 1)} className="px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800">←</button>
          <button
            onClick={() => onWeekChange(0)}
            className={`px-3 py-1 font-semibold ${weekOffset === 0 ? "bg-vju-500 text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}
          >
            Tuần này
          </button>
          <button onClick={() => onWeekChange(weekOffset + 1)} className="px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800">→</button>
        </div>
      </header>

      {!selectedDevice ? (
        <div className="p-10 text-center text-sm text-slate-500">Chọn 1 thiết bị để xem lịch.</div>
      ) : error ? (
        <div className="m-4 rounded-md border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {error}
        </div>
      ) : (
        <div className="relative">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/50 backdrop-blur-sm dark:bg-slate-950/50">
              <span className="text-xs text-slate-500">Đang tải...</span>
            </div>
          )}
          <div className="grid" style={{ gridTemplateColumns: "60px repeat(7, 1fr)" }}>
            <div className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50" />
            {days.map((d, i) => (
              <div
                key={i}
                className={`border-b border-l border-slate-200 px-2 py-2 text-center text-xs font-semibold dark:border-slate-800 ${
                  d.toDateString() === todayKey
                    ? "bg-vju-50 text-vju-700 dark:bg-vju-900/30 dark:text-vju-100"
                    : "bg-slate-50 text-slate-700 dark:bg-slate-800/50 dark:text-slate-300"
                }`}
              >
                {dayLabel(d)}
              </div>
            ))}

            <div className="bg-slate-50/50 dark:bg-slate-900/30">
              {Array.from({ length: TOTAL_ROWS }, (_, i) => (
                <div
                  key={i}
                  className="border-b border-slate-200 pr-2 pt-1 text-right font-mono text-[10px] text-slate-400 dark:border-slate-800"
                  style={{ height: HOUR_PX }}
                >
                  {pad(START_HOUR + i)}:00
                </div>
              ))}
            </div>

            {days.map((day, di) => (
              <DayColumn
                key={di}
                day={day}
                busy={data?.busy ?? []}
                expandedBookingId={expandedBookingId}
                onExpand={setExpandedBookingId}
                onEmptyCellClick={onEmptyCellClick}
                onCancel={onCancel}
                onConnect={onConnect}
              />
            ))}
          </div>

          <p className="border-t border-slate-200 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-800">
            ⓘ Click ô trống = đặt slot · click block = xem chi tiết / Connect / Cancel · 07:00–23:00.
          </p>
        </div>
      )}
    </div>
  );
}

function DayColumn({
  day,
  busy,
  expandedBookingId,
  onExpand,
  onEmptyCellClick,
  onCancel,
  onConnect,
}: {
  day: Date;
  busy: BusySlot[];
  expandedBookingId: string | null;
  onExpand: (id: string | null) => void;
  onEmptyCellClick: (cellDate: Date) => void;
  onCancel: (bookingId: string) => void;
  onConnect: (bookingId: string) => void;
}) {
  const dayBusy = busy.filter((b) => {
    const bs = new Date(b.start);
    return bs.toDateString() === day.toDateString();
  });

  return (
    <div
      className="relative border-l border-slate-200 dark:border-slate-800"
      style={{ height: HOUR_PX * TOTAL_ROWS }}
    >
      {Array.from({ length: TOTAL_ROWS }, (_, i) => {
        const cellDate = new Date(day);
        cellDate.setHours(START_HOUR + i, 0, 0, 0);
        return (
          <button
            type="button"
            key={i}
            onClick={() => onEmptyCellClick(cellDate)}
            className="block w-full border-b border-slate-100 transition hover:bg-vju-50/60 hover:ring-1 hover:ring-inset hover:ring-vju-400 dark:border-slate-800/60 dark:hover:bg-vju-900/30"
            style={{ height: HOUR_PX }}
            aria-label={`Đặt slot ${pad(START_HOUR + i)}:00`}
          />
        );
      })}
      {dayBusy.map((b) => (
        <BusyBlock
          key={b.booking_id}
          slot={b}
          expanded={expandedBookingId === b.booking_id}
          onExpand={() => onExpand(expandedBookingId === b.booking_id ? null : b.booking_id)}
          onCancel={onCancel}
          onConnect={onConnect}
        />
      ))}
    </div>
  );
}

function BusyBlock({
  slot,
  expanded,
  onExpand,
  onCancel,
  onConnect,
}: {
  slot: BusySlot;
  expanded: boolean;
  onExpand: () => void;
  onCancel: (id: string) => void;
  onConnect: (id: string) => void;
}) {
  const s = new Date(slot.start);
  const e = new Date(slot.end);
  const startMin = (s.getHours() - START_HOUR) * 60 + s.getMinutes();
  const durMin = (e.getTime() - s.getTime()) / 60_000;
  if (startMin < 0 || startMin >= TOTAL_ROWS * 60) return null;
  const top = (startMin / 60) * HOUR_PX;
  const height = Math.max(22, (durMin / 60) * HOUR_PX);

  const timeLabel = `${pad(s.getHours())}:${pad(s.getMinutes())}–${pad(e.getHours())}:${pad(e.getMinutes())}`;
  const now = Date.now();
  const canConnect = slot.is_mine && now >= s.getTime() - 5 * 60_000 && now < e.getTime();
  const canCancel = slot.is_mine;

  const color = slot.is_mine
    ? "bg-vju-500/85 border-vju-600 text-white shadow-md hover:bg-vju-500"
    : "bg-slate-400/70 border-slate-500 text-white hover:bg-slate-500";

  return (
    <button
      type="button"
      onClick={(ev) => {
        ev.stopPropagation();
        onExpand();
      }}
      className={`absolute inset-x-1 cursor-pointer rounded-md border px-1.5 py-1 text-left text-[10px] transition ${color} ${expanded ? "z-20 ring-2 ring-offset-1 ring-vju-300" : "z-10"}`}
      style={{ top, height: expanded ? Math.max(height, 92) : height }}
      title={`${slot.display} · ${timeLabel}`}
    >
      <p className="truncate font-mono font-bold leading-tight">{slot.display}</p>
      <p className="truncate text-[9px] opacity-85">{timeLabel}</p>
      {expanded && (
        <div
          className="mt-1 flex flex-wrap gap-1 border-t border-white/30 pt-1"
          onClick={(ev) => ev.stopPropagation()}
        >
          {canConnect && (
            <button
              type="button"
              onClick={() => onConnect(slot.booking_id)}
              className="inline-flex items-center gap-0.5 rounded bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white hover:bg-emerald-600"
            >
              <Power className="h-2.5 w-2.5" />
              Connect
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              onClick={() => onCancel(slot.booking_id)}
              className="inline-flex items-center gap-0.5 rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 hover:bg-white"
            >
              <X className="h-2.5 w-2.5" />
              Cancel
            </button>
          )}
          {!slot.is_mine && (
            <span className="text-[10px] opacity-90">
              Slot đã có người đặt.
            </span>
          )}
        </div>
      )}
    </button>
  );
}

export default function BookingsPage() {
  return (
    <AuthGate>
      <BookingsInner />
    </AuthGate>
  );
}
