"use client";

import { CalendarDays, Clock, Info, Loader2, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiPost, useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

// Each day has 6 blocks of 4h. We pick UTC-aligned starts so the backend's
// "must align to block boundary" check passes regardless of the user's TZ.
const BLOCKS_PER_DAY = 6;
const BLOCK_HOURS = 4;
const DAYS_AHEAD = 7;
const MAX_BLOCKS_AUTO = 6;

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

type CellState = "free" | "mine" | "taken" | "past";

export function BlockCalendarModal({
  deviceId,
  deviceName,
  onClose,
  onChanged,
}: BlockCalendarModalProps) {
  const { user } = useUser();
  const [bookings, setBookings] = useState<BlockBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // cellKey while submitting
  const [selectionStart, setSelectionStart] = useState<string | null>(null); // cellKey

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

  // ESC closes the modal
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Build a Map<cellKey, BlockBooking[]> — a single booking may span multiple
  // cells, so we explode it onto each block it covers.
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

  // Build the day grid — today + 6 days ahead, in UTC days (matches backend).
  const days = useMemo(() => {
    const now = new Date();
    const startDay = utcMidnight(now);
    return Array.from({ length: DAYS_AHEAD }, (_, i) =>
      new Date(startDay.getTime() + i * 86_400_000),
    );
  }, []);

  const cellState = useCallback(
    (day: Date, blockIdx: number): { state: CellState; booking?: BlockBooking } => {
      const blockStartT = blockStart(day, blockIdx);
      const blockEndT = new Date(blockStartT.getTime() + BLOCK_HOURS * 3600_000);
      const nowMs = Date.now();
      if (blockEndT.getTime() <= nowMs) return { state: "past" };

      const key = `${day.toISOString().slice(0, 10)}|${blockIdx}`;
      const b = occupancy.get(key);
      if (b) return { state: b.is_mine ? "mine" : "taken", booking: b };
      return { state: "free" };
    },
    [occupancy],
  );

  const cellKey = (day: Date, blockIdx: number) =>
    `${day.toISOString().slice(0, 10)}|${blockIdx}`;

  // Selection logic: click one cell → preview 1 block. Click a second cell on
  // SAME day, LATER block → range. Click anything else → reset.
  const handleClick = async (day: Date, blockIdx: number) => {
    const { state, booking } = cellState(day, blockIdx);
    if (state === "past") return;
    if (state === "taken") return; // someone else owns it

    if (state === "mine" && booking) {
      // cancel my booking — only if it hasn't started yet (the backend
      // re-validates; we soften the UX by warning here)
      const startMs = new Date(booking.start_time).getTime();
      if (startMs <= Date.now()) {
        alert("Block này đã bắt đầu, không huỷ được.");
        return;
      }
      if (!confirm(`Huỷ block ${fmtBlockLabel(blockIdx)} ngày ${fmtDayHeader(day).date}?`)) return;
      setBusy(cellKey(day, blockIdx));
      const r = await fetch(`${API}/vps-access/${deviceId}/blocks/${booking.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      setBusy(null);
      if (r.ok) {
        await refresh();
        onChanged?.();
      } else {
        const e = await r.json().catch(() => ({}));
        setErr(`Không huỷ được: ${e?.detail?.code || `HTTP ${r.status}`}`);
      }
      return;
    }

    // free cell
    const key = cellKey(day, blockIdx);
    if (selectionStart === null) {
      setSelectionStart(key);
      return;
    }
    if (selectionStart === key) {
      // double-click same cell → book just this one block
      await bookRange(day, blockIdx, blockIdx);
      setSelectionStart(null);
      return;
    }
    // try range
    const [startDay, startIdxStr] = selectionStart.split("|");
    const startIdx = parseInt(startIdxStr, 10);
    if (startDay !== day.toISOString().slice(0, 10)) {
      // different day — restart selection
      setSelectionStart(key);
      return;
    }
    const [from, to] = startIdx <= blockIdx ? [startIdx, blockIdx] : [blockIdx, startIdx];
    await bookRange(day, from, to);
    setSelectionStart(null);
  };

  const bookRange = async (day: Date, fromIdx: number, toIdx: number) => {
    // Sanity-check that the whole range is free (avoid the obvious race)
    for (let i = fromIdx; i <= toIdx; i++) {
      const s = cellState(day, i);
      if (s.state !== "free") {
        setErr("Có block trong dải đã có người đặt — hãy chọn lại");
        return;
      }
    }
    const blocks = toIdx - fromIdx + 1;
    if (blocks > MAX_BLOCKS_AUTO) {
      setErr(
        `Tối đa ${MAX_BLOCKS_AUTO} block (24h) cho auto. Cần dài hơn → gửi proposal.`,
      );
      return;
    }
    const startISO = blockStart(day, fromIdx).toISOString();
    const endISO = blockStart(day, toIdx + 1).toISOString();
    setBusy(cellKey(day, fromIdx));
    const r = await apiPost(`/vps-access/${deviceId}/blocks`, {
      start_time: startISO,
      end_time: endISO,
    });
    setBusy(null);
    if (r.ok) {
      await refresh();
      onChanged?.();
    } else {
      const e = await r.json().catch(() => ({}));
      setErr(e?.detail?.message || e?.detail?.code || `HTTP ${r.status}`);
    }
  };

  const myFutureCount = bookings.filter(
    (b) => b.is_mine && new Date(b.end_time).getTime() > Date.now(),
  ).length;

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
                4h/block · 6 block/ngày · auto-approve, hàng đợi round-robin
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
          <p className="flex items-center gap-2 text-xs text-amber-900 dark:text-amber-200">
            <Info className="h-4 w-4 shrink-0" />
            <span>
              <strong>Quy tắc công bằng:</strong> mỗi SV chỉ giữ 1 block tương lai
              trên VPS này. Block đã chạy xong rồi mới book được tiếp — để SV khác
              có cơ hội. Cần block dài hơn 24h?{" "}
              <Link
                href="/vps-access"
                className="font-bold underline hover:text-amber-700"
                onClick={onClose}
              >
                Gửi proposal cho giảng viên
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
              {selectionStart && (
                <div className="mb-3 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200">
                  ✏️ Đã chọn block đầu. Click block thứ 2 (cùng ngày, sau block đầu)
                  để đặt nhiều block liền, hoặc click lại block đầu để book chỉ 1 block.{" "}
                  <button
                    type="button"
                    onClick={() => setSelectionStart(null)}
                    className="ml-1 underline"
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
                        return (
                          <th
                            key={i}
                            className="border border-slate-200 bg-slate-50 px-2 py-2 text-center font-semibold dark:border-slate-700 dark:bg-slate-900"
                          >
                            <div className="text-[10px] uppercase text-slate-400">
                              {h.wd}
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
                          const k = cellKey(d, idx);
                          const isSelected = selectionStart === k;
                          const cls =
                            state === "free"
                              ? isSelected
                                ? "bg-indigo-200 border-indigo-500 hover:bg-indigo-300 dark:bg-indigo-800 dark:border-indigo-400"
                                : "bg-white hover:bg-emerald-50 hover:border-emerald-300 cursor-pointer dark:bg-slate-950 dark:hover:bg-emerald-950/30"
                              : state === "mine"
                                ? "bg-emerald-100 border-emerald-400 hover:bg-rose-50 cursor-pointer dark:bg-emerald-900/40 dark:border-emerald-600"
                                : state === "taken"
                                  ? "bg-slate-100 border-slate-300 dark:bg-slate-800 dark:border-slate-700"
                                  : "bg-slate-50 border-slate-200 opacity-50 dark:bg-slate-900/50";
                          const clickable = state === "free" || state === "mine";
                          const label =
                            state === "mine"
                              ? "Của bạn"
                              : state === "taken" && booking
                                ? booking.student_name?.slice(0, 12) ||
                                  booking.student_email?.split("@")[0]?.slice(0, 12) ||
                                  "đã đặt"
                                : state === "past"
                                  ? "qua"
                                  : "";
                          return (
                            <td
                              key={di}
                              onClick={
                                clickable && !busy ? () => handleClick(d, idx) : undefined
                              }
                              className={`border px-2 py-2 text-center text-[10px] font-semibold transition ${cls}`}
                              title={
                                state === "free"
                                  ? "Click để đặt block"
                                  : state === "mine"
                                    ? "Click để huỷ"
                                    : state === "taken" && booking
                                      ? `${booking.student_email || ""}`
                                      : ""
                              }
                            >
                              {busy === k ? (
                                <Loader2 className="mx-auto h-3 w-3 animate-spin" />
                              ) : (
                                <span className="block truncate">{label}</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <Legend color="bg-white border border-slate-300" label="Trống — click để book" />
                <Legend color="bg-emerald-100 border border-emerald-400" label="Bạn đã đặt — click huỷ" />
                <Legend color="bg-slate-100 border border-slate-300" label="SV khác đặt" />
                <Legend color="bg-slate-50 opacity-50" label="Đã qua" />
                <span className="ml-auto inline-flex items-center gap-1 rounded-md bg-indigo-100 px-2 py-1 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
                  <Clock className="h-3 w-3" />
                  Bạn đang giữ: <strong>{myFutureCount}</strong> block tương lai
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-3 w-5 rounded ${color}`} />
      {label}
    </span>
  );
}
