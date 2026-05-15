"use client";

import { Calendar, Loader2, Sparkles, Clock, X, ExternalLink, KeyRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Device } from "@/components/DeviceCard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function isoToLocalInput(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function nextHourLocal(): string {
  const d = new Date();
  d.setHours(d.getHours() + 1, 0, 0, 0);
  return isoToLocalInput(d.toISOString());
}

function plusHours(localIso: string, hours: number): string {
  const d = new Date(localIso);
  d.setHours(d.getHours() + hours);
  return isoToLocalInput(d.toISOString());
}

type Suggestion = { start: string; end: string };

export interface BookingModalProps {
  device: Device;
  onClose: () => void;
  onBooked: () => void;
}

export function BookingModal({ device, onClose, onBooked }: BookingModalProps) {
  const [start, setStart] = useState(nextHourLocal());
  const [end, setEnd] = useState(plusHours(nextHourLocal(), 2));
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggLoading, setSuggLoading] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  const durationHours = useMemo(() => {
    const s = new Date(start).getTime();
    const e = new Date(end).getTime();
    const h = (e - s) / 3600_000;
    return h > 0 && h <= 8 ? h : 2;
  }, [start, end]);

  // Preload suggestions on first open
  useEffect(() => {
    setSuggLoading(true);
    fetch(
      `${API}/devices/${device.id}/suggest-slots?duration_hours=${durationHours}&days=7&count=5`,
      { credentials: "include" },
    )
      .then((r) => (r.ok ? r.json() : { suggestions: [] }))
      .then((d) => setSuggestions(d.suggestions ?? []))
      .finally(() => setSuggLoading(false));
  }, [device.id, durationHours]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const r = await fetch(`${API}/bookings`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: device.id,
          start_time: new Date(start).toISOString(),
          end_time: new Date(end).toISOString(),
          notes: notes || null,
        }),
      });
      if (r.ok) {
        setResult({
          ok: true,
          msg: "✓ Đặt lịch thành công. Đến giờ vào Bookings → Connect để mở terminal.",
        });
        setTimeout(onBooked, 1200);
      } else {
        const err = await r.json().catch(() => ({}));
        const code = err?.detail?.code ?? "ERROR";
        const friendly: Record<string, string> = {
          BOOKING_CONFLICT: "Slot này trùng với lịch khác — chọn slot trống dưới đây.",
          ACCESS_DENIED:
            "Bạn chưa được giảng viên cấp quyền cho kit này. Liên hệ giảng viên.",
          OUTSIDE_CLASS_WINDOW: "Slot nằm ngoài khung giờ lớp được phép.",
          QUOTA_EXCEEDED: "Hết quota tuần này.",
          DURATION_EXCEEDED: "Slot dài quá giới hạn (8h).",
          DEVICE_NOT_FOUND: "Không tìm thấy thiết bị.",
        };
        setResult({ ok: false, msg: friendly[code] ?? `Lỗi: ${code}` });
      }
    } catch (e) {
      setResult({ ok: false, msg: String(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const apply = (s: Suggestion) => {
    setStart(isoToLocalInput(s.start));
    setEnd(isoToLocalInput(s.end));
    setResult(null);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/60 p-4 backdrop-blur-sm md:items-center"
      onClick={onClose}
    >
      <div
        className="surface w-full max-w-lg overflow-hidden p-0"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-200 bg-gradient-to-r from-vju-500 to-vju-700 px-5 py-4 text-white dark:border-slate-700">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest opacity-80">
              Đặt slot
            </p>
            <h2 className="text-lg font-bold leading-tight">
              {device.name} · {device.model}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-white/80 hover:bg-white/10 hover:text-white"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <form onSubmit={submit} className="flex flex-col gap-4 p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
              Bắt đầu
              <input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                required
              />
            </label>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
              Kết thúc
              <input
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                required
              />
            </label>
          </div>
          <p className="-mt-2 text-[11px] text-slate-500">
            Slot dài {durationHours.toFixed(1)}h · giới hạn 8h · không vượt quota tuần.
          </p>

          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
            Ghi chú (optional)
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              maxLength={500}
              placeholder="VD: Synthesize bitstream cho thí nghiệm 3"
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>

          {result && (
            <div
              className={`rounded-md border p-3 text-xs ${
                result.ok
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200"
                  : "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200"
              }`}
            >
              {result.msg}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 px-4 py-3 text-sm font-bold text-white shadow-md hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calendar className="h-4 w-4" />}
            Xác nhận đặt slot
          </button>

          <details className="rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50">
            <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-semibold">
              <Sparkles className="h-3.5 w-3.5 text-accent-500" />
              Gợi ý {suggLoading ? "..." : `${suggestions.length} slot trống`} ({durationHours.toFixed(1)}h)
            </summary>
            <ul className="space-y-1 px-3 py-2 pt-0">
              {suggestions.length === 0 && !suggLoading && (
                <li className="py-1 text-xs text-slate-500">
                  Không có slot trống nào trong 7 ngày tới với độ dài này.
                </li>
              )}
              {suggestions.map((s, i) => {
                const sd = new Date(s.start);
                const ed = new Date(s.end);
                return (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => apply(s)}
                      className="flex w-full items-center justify-between rounded-md bg-white px-3 py-1.5 text-xs hover:bg-vju-50 dark:bg-slate-800 dark:hover:bg-slate-700"
                    >
                      <span className="inline-flex items-center gap-2">
                        <Clock className="h-3 w-3 text-slate-400" />
                        <span className="font-mono font-semibold">
                          {sd.toLocaleString("vi-VN", {
                            weekday: "short",
                            day: "2-digit",
                            month: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        <span className="text-slate-400">→</span>
                        <span className="font-mono">
                          {ed.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </span>
                      <span className="rounded bg-vju-100 px-2 py-0.5 text-[10px] font-bold uppercase text-vju-700 dark:bg-vju-900/40 dark:text-vju-100">
                        Chọn
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </details>
        </form>
      </div>
    </div>
  );
}

export interface SessionResult {
  session_id: string;
  ssh_user: string;
  ssh_host: string;
  ssh_port: number;
  private_key: string;
  wetty_url: string;
  fingerprint: string;
  mocked: boolean;
}

export interface SessionLaunchModalProps {
  session: SessionResult;
  onClose: () => void;
}

export function SessionLaunchModal({ session, onClose }: SessionLaunchModalProps) {
  const [copied, setCopied] = useState(false);
  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(session.private_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="surface w-full max-w-2xl overflow-hidden p-0"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-200 bg-gradient-to-r from-emerald-500 to-teal-600 px-5 py-4 text-white dark:border-slate-700">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest opacity-80">
              Session sẵn sàng {session.mocked && "(mock — backend chưa thấy device)"}
            </p>
            <h2 className="text-lg font-bold leading-tight">
              SSH {session.ssh_user}@{session.ssh_host}:{session.ssh_port}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-white/80 hover:bg-white/10 hover:text-white"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="space-y-4 p-5">
          <a
            href={session.wetty_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-vju-500 to-vju-700 px-4 py-3 text-sm font-bold text-white shadow-md hover:shadow-lg"
          >
            <ExternalLink className="h-4 w-4" />
            Mở web terminal (wetty) trong tab mới
          </a>

          <details className="rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50">
            <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-semibold">
              <KeyRound className="h-3.5 w-3.5 text-accent-500" />
              Hoặc dùng SSH client native (private key chỉ hiện 1 lần)
            </summary>
            <div className="space-y-2 px-3 py-2 pt-0">
              <p className="text-[11px] text-slate-500">
                Lưu key vào file (vd <code className="rounded bg-slate-200 px-1 dark:bg-slate-700">~/.ssh/vju-session</code>), chmod 600, rồi:
              </p>
              <pre className="overflow-x-auto rounded-md bg-slate-900 px-3 py-2 font-mono text-[11px] text-emerald-300">
                ssh -i ~/.ssh/vju-session -p {session.ssh_port} {session.ssh_user}@{session.ssh_host}
              </pre>
              <button
                type="button"
                onClick={copyKey}
                className="rounded-md border border-slate-300 bg-white px-3 py-1 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
              >
                {copied ? "✓ Đã copy private key" : "Copy private key"}
              </button>
              <textarea
                readOnly
                value={session.private_key}
                rows={8}
                className="block w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-[10px] text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
              />
            </div>
          </details>

          <p className="text-[11px] text-slate-500">
            Fingerprint: <code className="font-mono">{session.fingerprint}</code>
          </p>
        </div>
      </div>
    </div>
  );
}
