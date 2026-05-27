"use client";

import { CalendarDays, Check, Clock, Info, Loader2, ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiPost } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

const BLOCKS_PER_DAY = 4;
const BLOCK_HOURS = 6;
const DAYS_AHEAD = 7;
const MAX_BLOCKS_PER_BOOKING = 4; // 24h ceiling, matches backend MAX_BLOCKS_AUTO

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
  | "free"        // free + in present/future, clickable to book
  | "mine-auto"   // SV's own auto block-booking, clickable to cancel
  | "mine-grant"  // SV has a long lecturer-granted access spanning this slot
  | "taken";      // someone else booked / has a grant — read-only

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
  // Range selection: first click sets the anchor, second click in the SAME day
  // and later block confirms. ESC or click outside resets.
  const [rangeAnchor, setRangeAnchor] = useState<{ day: Date; blockIdx: number } | null>(null);
  // Confirm dialog state — either a book (range) or a cancel action.
  const [confirmAction, setConfirmAction] = useState<
    | { kind: "book"; day: Date; fromIdx: number; toIdx: number }
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
      const endT = blockEnd(day, blockIdx).getTime();
      const nowMs = Date.now();
      if (endT <= nowMs) {
        const key = `${day.toISOString().slice(0, 10)}|${blockIdx}`;
        return { state: "past", booking: occupancy.get(key) };
      }
      const key = `${day.toISOString().slice(0, 10)}|${blockIdx}`;
      const b = occupancy.get(key);
      if (!b) return { state: "free" };
      if (b.is_mine) {
        // Auto block-bookings can be cancelled from this UI; lecturer-granted
        // long access (granted_via='special_access') is read-only here —
        // student would email the lecturer to release it.
        return {
          state: b.granted_via === "auto" ? "mine-auto" : "mine-grant",
          booking: b,
        };
      }
      return { state: "taken", booking: b };
    },
    [occupancy],
  );

  const onCellClick = (day: Date, blockIdx: number) => {
    if (busy || confirmAction) return;
    const { state, booking } = cellState(day, blockIdx);

    if (state === "mine-auto" && booking) {
      setRangeAnchor(null);
      setConfirmAction({ kind: "cancel", booking, day, blockIdx });
      return;
    }
    if (state !== "free") {
      // past / taken / mine-grant → not clickable
      return;
    }

    // free cell — range selection
    if (rangeAnchor === null) {
      setRangeAnchor({ day, blockIdx });
      return;
    }
    const sameDay =
      rangeAnchor.day.toISOString().slice(0, 10) === day.toISOString().slice(0, 10);
    if (!sameDay) {
      // different day → reset anchor to the new cell
      setRangeAnchor({ day, blockIdx });
      return;
    }
    const fromIdx = Math.min(rangeAnchor.blockIdx, blockIdx);
    const toIdx = Math.max(rangeAnchor.blockIdx, blockIdx);
    // Sanity: every block in [from, to] must be free
    for (let i = fromIdx; i <= toIdx; i++) {
      if (cellState(day, i).state !== "free") {
        setErr("Dải chọn có block đã có người đặt — hãy chọn lại.");
        setRangeAnchor(null);
        return;
      }
    }
    const span = toIdx - fromIdx + 1;
    if (span > MAX_BLOCKS_PER_BOOKING) {
      setErr(
        `Tối đa ${MAX_BLOCKS_PER_BOOKING} block/lần (${MAX_BLOCKS_PER_BOOKING * BLOCK_HOURS}h). ` +
          `Cần dài hơn → email giảng viên xin grant.`,
      );
      setRangeAnchor(null);
      return;
    }
    setRangeAnchor(null);
    setConfirmAction({ kind: "book", day, fromIdx, toIdx });
  };

  const submitBook = async () => {
    if (!confirmAction || confirmAction.kind !== "book") return;
    setBusy(true);
    const startISO = blockStart(confirmAction.day, confirmAction.fromIdx).toISOString();
    const endISO = blockEnd(confirmAction.day, confirmAction.toIdx).toISOString();
    const r = await apiPost(`/vps-access/${deviceId}/blocks`, {
      start_time: startISO,
      end_time: endISO,
    });
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
              <strong>Mỗi SV chỉ giữ 1 lịch tại 1 lúc.</strong> Click 1 block để
              chọn, click block thứ 2 cùng ngày để đặt dải (tối đa{" "}
              {MAX_BLOCKS_PER_BOOKING} block = {MAX_BLOCKS_PER_BOOKING * BLOCK_HOURS}h).
              Đến giờ là vào dùng. Lịch chạy xong (hoặc huỷ) mới đặt được lịch mới.
              Cần dài hơn 24h?{" "}
              <Link
                href="/vps-access"
                className="font-bold underline hover:text-amber-700"
                onClick={onClose}
              >
                Soạn proposal cho GV
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
              {rangeAnchor && (
                <div className="mb-3 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200">
                  ✏️ Đã chọn block đầu ({fmtBlockLabel(rangeAnchor.blockIdx)}, {fmtDayHeader(rangeAnchor.day).date}).
                  Click block thứ 2 cùng ngày (sau hoặc trước cũng được) để đặt dải, hoặc click lại block đầu để chỉ đặt 1 block.{" "}
                  <button
                    type="button"
                    onClick={() => setRangeAnchor(null)}
                    className="ml-1 font-bold underline"
                  >
                    Bỏ chọn
                  </button>
                </div>
              )}
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
                          const clickable = state === "free" || state === "mine-auto";
                          const isAnchor =
                            rangeAnchor !== null &&
                            rangeAnchor.day.toISOString().slice(0, 10) === d.toISOString().slice(0, 10) &&
                            rangeAnchor.blockIdx === idx;
                          const styles = cellStyle(state, isAnchor);
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
                <Legend color="bg-emerald-500" label="Trống — click để đặt" />
                <Legend color="bg-indigo-500" label="Bạn đặt (auto) — click huỷ" />
                <Legend color="bg-violet-300 dark:bg-violet-800" label="Bạn có grant từ GV" />
                <Legend color="bg-rose-300 dark:bg-rose-900" label="SV khác giữ" />
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

function cellStyle(state: CellState, isAnchor = false): string {
  if (isAnchor) {
    return "bg-amber-300 border-amber-500 text-amber-950 ring-2 ring-amber-500 dark:bg-amber-700 dark:border-amber-400 dark:text-amber-50";
  }
  switch (state) {
    case "past":
      return "bg-slate-100 border-slate-200 opacity-40 dark:bg-slate-900/50 dark:border-slate-800 text-slate-500";
    case "free":
      return "bg-emerald-500 border-emerald-600 text-white hover:bg-emerald-600 dark:bg-emerald-600/80 dark:border-emerald-500";
    case "mine-auto":
      return "bg-indigo-500 border-indigo-600 text-white hover:bg-rose-500 dark:bg-indigo-600 dark:border-indigo-500";
    case "mine-grant":
      return "bg-violet-300 border-violet-400 text-violet-900 dark:bg-violet-800 dark:border-violet-700 dark:text-violet-100";
    case "taken":
    default:
      return "bg-rose-300 border-rose-400 text-rose-950 dark:bg-rose-900/70 dark:border-rose-700 dark:text-rose-100";
  }
}

function cellLabel(state: CellState, booking: BlockBooking | undefined): string {
  switch (state) {
    case "past":
      return "qua";
    case "free":
      return "trống";
    case "mine-auto":
      return "Của bạn — huỷ";
    case "mine-grant":
      return "Bạn (grant GV)";
    case "taken":
    default:
      return booking
        ? booking.student_name?.slice(0, 14) ||
            booking.student_email?.split("@")[0]?.slice(0, 14) ||
            "đã đặt"
        : "đã đặt";
  }
}

function cellTitle(state: CellState, booking: BlockBooking | undefined): string {
  switch (state) {
    case "free":
      return "Click để chọn — click block thứ 2 cùng ngày để đặt dải";
    case "mine-auto":
      return "Block bạn đã đặt — click để huỷ";
    case "mine-grant":
      return "Grant dài hạn của bạn (GV cấp) — quản lý ở /vps-access";
    case "taken":
      return booking ? `Đã đặt: ${booking.student_email || ""}` : "Đã đặt";
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
  action:
    | { kind: "book"; day: Date; fromIdx: number; toIdx: number }
    | { kind: "cancel"; booking: BlockBooking; blockIdx: number; day: Date };
  busy: boolean;
  deviceName: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const isBook = action.kind === "book";
  const start =
    action.kind === "book"
      ? blockStart(action.day, action.fromIdx)
      : blockStart(action.day, action.blockIdx);
  const end =
    action.kind === "book"
      ? blockEnd(action.day, action.toIdx)
      : blockEnd(action.day, action.blockIdx);
  const blockCount =
    action.kind === "book" ? action.toIdx - action.fromIdx + 1 : 1;
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
              {fmtTime(start)} – {fmtTime(end)} ({blockCount * BLOCK_HOURS} giờ
              {blockCount > 1 ? ` · ${blockCount} block liền` : ""})
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
