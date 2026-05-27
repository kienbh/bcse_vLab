"use client";

import { CalendarDays, Check, Clock, Info, Loader2, ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiPost } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

const BLOCKS_PER_DAY = 6;
const BLOCK_HOURS = 4;
const DAYS_AHEAD = 7;

export type BlockBooking = {
  id: string;
  user_id: string;
  device_id: string;
  start_time: string;
  end_time: string;
  status: string;
  granted_via: string;
  student_email: string | null;
  student_name: string | null;
  is_mine: boolean;
};

export interface BlockCalendarModalProps {
  deviceId: string;
  deviceName: string;
  onClose: () => void;
  onChanged?: () => void;
}

/** UTC midnight of the given local Date. */
function utcMidnight(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
}

function blockStart(dayUtc: Date, blockIdx: number): Date {
  return new Date(dayUtc.getTime() + blockIdx * BLOCK_HOURS * 3600_000);
}

function blockEnd(dayUtc: Date, blockIdx: number): Date {
  return new Date(blockStart(dayUtc, blockIdx).getTime() + BLOCK_HOURS * 3600_000);
}

function fmtBlockLabel(blockIdx: number): string {
  const startH = blockIdx * BLOCK_HOURS;
  const endH = startH + BLOCK_HOURS;
  return `${String(startH).padStart(2, "0")}:00–${String(endH).padStart(2, "0")}:00`;
}

function fmtDayHeader(d: Date): { wd: string; date: string } {
  const wd = d.toLocaleDateString("vi-VN", { weekday: "short", timeZone: "UTC" });
  const date = d.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  });
  return { wd, date };
}

type CellState =
  | "past"
  | "current-free"  // the block in progress, free → student can book NOW
  | "current-mine"  // I'm the one holding this current block
  | "current-taken" // someone else has this current block
  | "future-free"   // visible for planning but not bookable yet
  | "future-taken"  // someone else booked ahead (only possible for grants)
  | "future-mine"; // shouldn't happen under single-block rule; defensive

export function BlockCalendarModal({
  deviceId,
  deviceName,
  onClose,
  onChanged,
}: BlockCalendarModalProps) {
  const [bookings, setBookings] = useState<BlockBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Confirm dialog state — either a book or a cancel action waiting for OK.
  const [confirmAction, setConfirmAction] = useState<
    | { kind: "book"; day: Date; blockIdx: number }
    | { kind: "cancel"; booking: BlockBooking; blockIdx: number; day: Date }
    | null
  >(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`${API}/vps-access/${deviceId}/blocks?days=${DAYS_AHEAD}`, {
        credentials: "include",
        cache: "no-store",
      });
      if (r.ok) {
        setBookings(await r.json());
      } else {
        setErr(`HTTP ${r.status}`);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // ESC closes the calendar (but not if a confirm dialog is open — ESC closes that first)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (confirmAction) setConfirmAction(null);
      else onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmAction, onClose]);

  // Each cell can be owned by at most one booking; map cellKey → booking.
  const occupancy = useMemo(() => {
    const m = new Map<string, BlockBooking>();
    for (const b of bookings) {
      const start = new Date(b.start_time);
      const end = new Date(b.end_time);
      let cur = start.getTime();
      while (cur < end.getTime()) {
        const dayUtc = utcMidnight(new Date(cur));
        const blockIdx = Math.floor(
          (cur - dayUtc.getTime()) / (BLOCK_HOURS * 3600_000),
        );
        const key = `${dayUtc.toISOString().slice(0, 10)}|${blockIdx}`;
        m.set(key, b);
        cur += BLOCK_HOURS * 3600_000;
      }
    }
    return m;
  }, [bookings]);

  const days = useMemo(() => {
    const startDay = utcMidnight(new Date());
    return Array.from({ length: DAYS_AHEAD }, (_, i) =>
      new Date(startDay.getTime() + i * 86_400_000),
    );
  }, []);

  const cellState = useCallback(
    (day: Date, blockIdx: number): { state: CellState; booking?: BlockBooking } => {
      const startT = blockStart(day, blockIdx).getTime();
      const endT = blockEnd(day, blockIdx).getTime();
      const nowMs = Date.now();
      const isCurrent = startT <= nowMs && nowMs < endT;
      const isPast = endT <= nowMs;

      const key = `${day.toISOString().slice(0, 10)}|${blockIdx}`;
      const b = occupancy.get(key);

      if (isPast) return { state: "past", booking: b };
      if (isCurrent) {
        if (!b) return { state: "current-free" };
        return { state: b.is_mine ? "current-mine" : "current-taken", booking: b };
      }
      // future
      if (!b) return { state: "future-free" };
      return { state: b.is_mine ? "future-mine" : "future-taken", booking: b };
    },
    [occupancy],
  );

  const cellKey = (day: Date, blockIdx: number) =>
    `${day.toISOString().slice(0, 10)}|${blockIdx}`;

  const onCellClick = (day: Date, blockIdx: number) => {
    if (busy || confirmAction) return;
    const { state, booking } = cellState(day, blockIdx);
    if (state === "current-free") {
      setConfirmAction({ kind: "book", day, blockIdx });
    } else if (state === "current-mine" && booking) {
      setConfirmAction({ kind: "cancel", booking, day, blockIdx });
    }
    // past / future / taken → no action
  };

  const submitBook = async () => {
    if (!confirmAction || confirmAction.kind !== "book") return;
    setBusy(true);
    const r = await apiPost(`/vps-access/${deviceId}/blocks/current`);
    setBusy(false);
    if (r.ok) {
      setConfirmAction(null);
      await refresh();
      onChanged?.();
    } else {
      const e = await r.json().catch(() => ({}));
      setErr(e?.detail?.message || e?.detail?.code || `HTTP ${r.status}`);
      setConfirmAction(null);
    }
  };

  const submitCancel = async () => {
    if (!confirmAction || confirmAction.kind !== "cancel") return;
    setBusy(true);
    const r = await fetch(
      `${API}/vps-access/${deviceId}/blocks/${confirmAction.booking.id}`,
      { method: "DELETE", credentials: "include" },
    );
    setBusy(false);
    if (r.ok) {
      setConfirmAction(null);
      await refresh();
      onChanged?.();
    } else {
      const e = await r.json().catch(() => ({}));
      setErr(e?.detail?.message || e?.detail?.code || `HTTP ${r.status}`);
      setConfirmAction(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[55] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-5xl overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-950"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-gradient-to-r from-indigo-500 to-indigo-700 px-5 py-4 text-white dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-white/20 backdrop-blur-sm">
              <CalendarDays className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-tight">
                Lịch block · {deviceName}
              </h2>
              <p className="text-xs text-white/85">
                4h/block · 6 block/ngày · click block ĐANG CHẠY để đặt
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-white/15 px-2 py-1 text-white hover:bg-white/25"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="border-b border-slate-200 bg-amber-50 px-5 py-3 dark:border-slate-800 dark:bg-amber-950/30">
          <p className="flex items-start gap-2 text-xs text-amber-900 dark:text-amber-200">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              <strong>Chỉ click được block đang chạy bây giờ.</strong> Mỗi SV
              giữ tối đa 1 block tại 1 thời điểm trên toàn hệ thống VPS.
              Block tương lai chỉ để xem trước — đợi đến giờ mới đặt được.
              Cần dài hơn 24h?{" "}
              <Link
                href="/vps-access"
                className="font-bold underline hover:text-amber-700"
                onClick={onClose}
              >
                Email giảng viên xin proposal
              </Link>
              .
            </span>
          </p>
        </div>

        {err && (
          <div className="border-b border-rose-300 bg-rose-50 px-5 py-2 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
            {err}
          </div>
        )}

        <div className="max-h-[60vh] overflow-auto p-4">
          {loading ? (
            <div className="flex items-center gap-2 p-8 text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Đang tải lịch...
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>
                      <th className="sticky left-0 z-10 border border-slate-200 bg-slate-50 px-2 py-2 text-left text-[11px] font-bold uppercase text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                        Giờ (UTC)
                      </th>
                      {days.map((d, i) => {
                        const h = fmtDayHeader(d);
                        const isToday = i === 0;
                        return (
                          <th
                            key={i}
                            className={`border border-slate-200 px-2 py-2 text-center font-semibold dark:border-slate-700 ${
                              isToday
                                ? "bg-indigo-50 dark:bg-indigo-950/40"
                                : "bg-slate-50 dark:bg-slate-900"
                            }`}
                          >
                            <div className="text-[10px] uppercase text-slate-400">
                              {h.wd}
                              {isToday && " • HÔM NAY"}
                            </div>
                            <div className="text-xs">{h.date}</div>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: BLOCKS_PER_DAY }, (_, idx) => (
                      <tr key={idx}>
                        <td className="sticky left-0 z-10 border border-slate-200 bg-slate-50 px-2 py-1.5 font-mono text-[11px] font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                          {fmtBlockLabel(idx)}
                        </td>
                        {days.map((d, di) => {
                          const { state, booking } = cellState(d, idx);
                          const clickable =
                            state === "current-free" || state === "current-mine";
                          const styles = cellStyle(state);
                          const label = cellLabel(state, booking);
                          return (
                            <td
                              key={di}
                              onClick={clickable ? () => onCellClick(d, idx) : undefined}
                              className={`border px-2 py-2 text-center text-[10px] font-semibold transition ${styles} ${
                                clickable ? "cursor-pointer" : "cursor-default"
                              }`}
                              title={cellTitle(state, booking)}
                            >
                              <span className="block truncate">{label}</span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <Legend color="bg-emerald-500 ring-2 ring-emerald-300" label="Block ĐANG CHẠY — trống, click để đặt" />
                <Legend color="bg-indigo-500 ring-2 ring-indigo-300" label="Block của bạn — click để huỷ" />
                <Legend color="bg-rose-200 dark:bg-rose-900" label="Block đang chạy — SV khác giữ" />
                <Legend color="bg-slate-200" label="Tương lai — chỉ xem" />
                <Legend color="bg-slate-100 opacity-50" label="Đã qua" />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Confirm modal (nested) — for booking or cancelling */}
      {confirmAction && (
        <ConfirmModal
          action={confirmAction}
          busy={busy}
          deviceName={deviceName}
          onConfirm={confirmAction.kind === "book" ? submitBook : submitCancel}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </div>
  );
}

function cellStyle(state: CellState): string {
  switch (state) {
    case "past":
      return "bg-slate-100 border-slate-200 opacity-40 dark:bg-slate-900/50 dark:border-slate-800 text-slate-500";
    case "current-free":
      return "bg-emerald-500 border-emerald-600 text-white hover:bg-emerald-600 ring-2 ring-emerald-300 ring-offset-1 dark:ring-emerald-700";
    case "current-mine":
      return "bg-indigo-500 border-indigo-600 text-white hover:bg-rose-500 ring-2 ring-indigo-300 ring-offset-1 dark:ring-indigo-700";
    case "current-taken":
      return "bg-rose-200 border-rose-300 text-rose-900 dark:bg-rose-900/50 dark:border-rose-700 dark:text-rose-100";
    case "future-mine":
      return "bg-indigo-100 border-indigo-300 text-indigo-800 dark:bg-indigo-950/40 dark:border-indigo-700 dark:text-indigo-100";
    case "future-taken":
      return "bg-slate-200 border-slate-300 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200";
    case "future-free":
    default:
      return "bg-slate-50 border-slate-200 text-slate-400 dark:bg-slate-900/30 dark:border-slate-800";
  }
}

function cellLabel(state: CellState, booking: BlockBooking | undefined): string {
  switch (state) {
    case "past":
      return "qua";
    case "current-free":
      return "ĐẶT BLOCK NÀY";
    case "current-mine":
      return "Của bạn — click huỷ";
    case "current-taken":
    case "future-taken":
      return booking
        ? booking.student_name?.slice(0, 14) ||
            booking.student_email?.split("@")[0]?.slice(0, 14) ||
            "đã đặt"
        : "đã đặt";
    case "future-mine":
      return "bạn (grant)";
    case "future-free":
    default:
      return "";
  }
}

function cellTitle(state: CellState, booking: BlockBooking | undefined): string {
  switch (state) {
    case "current-free":
      return "Click để đặt block đang chạy";
    case "current-mine":
      return "Block đang chạy của bạn — click để huỷ";
    case "current-taken":
    case "future-taken":
      return booking ? `${booking.student_email || ""}` : "";
    case "future-free":
      return "Đợi đến giờ này rồi click để đặt";
    case "future-mine":
      return "Grant dài hạn của bạn (do GV cấp)";
    case "past":
      return "Block đã qua";
  }
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-3 w-5 rounded ${color}`} />
      {label}
    </span>
  );
}

function ConfirmModal({
  action,
  busy,
  deviceName,
  onConfirm,
  onCancel,
}: {
  action: { kind: "book" | "cancel"; day: Date; blockIdx: number; booking?: BlockBooking };
  busy: boolean;
  deviceName: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const isBook = action.kind === "book";
  const start = blockStart(action.day, action.blockIdx);
  const end = blockEnd(action.day, action.blockIdx);
  const fmtTime = (d: Date) =>
    d.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    });
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-xl bg-white shadow-2xl dark:bg-slate-950"
        onClick={(e) => e.stopPropagation()}
      >
        <header
          className={`flex items-center gap-3 px-5 py-4 text-white ${
            isBook
              ? "bg-gradient-to-r from-emerald-500 to-emerald-600"
              : "bg-gradient-to-r from-rose-500 to-rose-600"
          }`}
        >
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-white/20">
            {isBook ? <Check className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}
          </div>
          <h3 className="text-base font-bold">
            {isBook ? "Xác nhận đặt block" : "Xác nhận huỷ block"}
          </h3>
        </header>
        <div className="space-y-3 px-5 py-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              VPS
            </p>
            <p className="text-base font-bold">{deviceName}</p>
            <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">
              Khoảng thời gian (UTC)
            </p>
            <p className="font-mono text-sm font-bold text-indigo-700 dark:text-indigo-300">
              <Clock className="mr-1 inline h-3.5 w-3.5" />
              {fmtTime(start)} – {fmtTime(end)} (4 giờ)
            </p>
          </div>
          {isBook ? (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Bấm <strong>Xác nhận đặt</strong> để giữ block. Sau khi block bắt
              đầu, bạn vào card VPS bấm <em>Mở terminal SSH</em> để vào máy.
            </p>
          ) : (
            <p className="text-sm text-rose-700 dark:text-rose-300">
              Huỷ xong block sẽ trống ngay, SV khác có thể chiếm. Dữ liệu trong
              VPS KHÔNG bị xoá — chỉ là bạn không còn quyền SSH cho block này.
            </p>
          )}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3 dark:border-slate-800 dark:bg-slate-900">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            Bỏ qua
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-bold text-white shadow-md disabled:opacity-50 ${
              isBook
                ? "bg-emerald-600 hover:bg-emerald-700"
                : "bg-rose-600 hover:bg-rose-700"
            }`}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            {isBook ? "Xác nhận đặt" : "Huỷ block"}
          </button>
        </footer>
      </div>
    </div>
  );
}
