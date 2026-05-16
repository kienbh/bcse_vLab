"use client";

import { Calendar, Loader2, Sparkles, Clock, X, KeyRound, RefreshCw, Terminal } from "lucide-react";
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
  /** Optional prefilled start (local-input format YYYY-MM-DDTHH:MM). Used when opening from a calendar empty-cell click. */
  initialStart?: string;
  /** Optional prefilled end. Defaults to initialStart+2h. */
  initialEnd?: string;
}

export function BookingModal({ device, onClose, onBooked, initialStart, initialEnd }: BookingModalProps) {
  const [start, setStart] = useState(initialStart ?? nextHourLocal());
  const [end, setEnd] = useState(initialEnd ?? plusHours(initialStart ?? nextHourLocal(), 2));
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
          msg: "✓ Đặt lịch thành công. Đến giờ vào Bookings → Get SSH access để lấy password.",
        });
        setTimeout(onBooked, 1200);
      } else {
        const err = await r.json().catch(() => ({}));
        const code = err?.detail?.code ?? "ERROR";
        const friendly: Record<string, string> = {
          BOOKING_CONFLICT: "Slot này trùng với lịch khác — chọn slot trống.",
          ACCESS_DENIED: "Bạn chưa được giảng viên cấp quyền cho kit này. Liên hệ giảng viên.",
          NO_CLASS_ASSIGNMENT: "Kit này chưa được gán vào lớp nào của bạn.",
          NO_SPECIAL_ACCESS: "Bạn chưa có quyền cá nhân cho kit này.",
          OUTSIDE_TIME_WINDOW: "Slot nằm ngoài khung giờ lớp được phép.",
          OUTSIDE_CLASS_WINDOW: "Slot nằm ngoài khung giờ lớp được phép.",
          WEEKLY_QUOTA_EXCEEDED: "Hết quota tuần này cho lớp / kit này.",
          GLOBAL_WEEKLY_HOURS_EXCEEDED: "Hết quota tuần (cộng dồn mọi kit).",
          QUOTA_EXCEEDED: "Hết quota tuần này.",
          DURATION_EXCEEDED: "Slot dài quá giới hạn (tối đa 8h).",
          CONCURRENT_LIMIT_EXCEEDED: "Đã chạm giới hạn booking đồng thời cho kit này.",
          GLOBAL_CONCURRENT_LIMIT: "Đã chạm giới hạn booking đồng thời (mọi kit).",
          TOO_FAR_IN_ADVANCE: "Slot quá xa — chỉ được đặt trước 7 ngày.",
          PAST_TIME: "Slot ở quá khứ — chọn giờ tương lai.",
          INVALID_TIME_RANGE: "Giờ kết thúc phải sau giờ bắt đầu.",
          DEVICE_NOT_FOUND: "Không tìm thấy thiết bị.",
          DEVICE_NOT_AVAILABLE: "Thiết bị đang bảo trì hoặc offline.",
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

/** Response shape of POST /api/bookings/{id}/access (ADR-0013, M5.8). */
export interface SessionResult {
  session_id: string;
  password: string;        // hiện 1 lần — regenerate nếu mất
  ssh_username: string;    // 'vlab' (account trên gateway)
  jump_host: string;       // ssh.bcse-vju.com
  jump_port: number;       // 2222
  target_user: string;     // user trên kit (pi / student)
  target_host: string;     // IP nội bộ kit
  target_port: number;
  ssh_command: string;     // lệnh hoàn chỉnh paste vào terminal
  expires_at: string;
  issued_at: string;
  regenerate_count: number;
}

export interface SessionLaunchModalProps {
  session: SessionResult;
  bookingId: string;
  onClose: () => void;
  /** Re-issued session is bubbled up so the parent re-renders new password. */
  onSessionReplaced?: (next: SessionResult) => void;
}

export function SessionLaunchModal({
  session,
  bookingId,
  onClose,
  onSessionReplaced,
}: SessionLaunchModalProps) {
  const [current, setCurrent] = useState<SessionResult>(session);
  const [copiedPw, setCopiedPw] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [showPw, setShowPw] = useState(true);

  const copyPw = async () => {
    try {
      await navigator.clipboard.writeText(current.password);
      setCopiedPw(true);
      setTimeout(() => setCopiedPw(false), 1800);
    } catch {
      /* ignore */
    }
  };
  const copyCmd = async () => {
    try {
      await navigator.clipboard.writeText(current.ssh_command);
      setCopiedCmd(true);
      setTimeout(() => setCopiedCmd(false), 1800);
    } catch {
      /* ignore */
    }
  };

  const regenerate = async () => {
    if (
      !confirm(
        "Cấp password mới? Password hiện tại sẽ bị vô hiệu hoá ngay lập tức " +
        "(dùng khi password đã lộ hoặc bạn quên).",
      )
    )
      return;
    setRegenLoading(true);
    setRegenError(null);
    try {
      const r = await fetch(
        `${API}/bookings/${bookingId}/access/regenerate`,
        { method: "POST", credentials: "include" },
      );
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        setRegenError(e?.detail?.code ?? "REGENERATE_FAILED");
        return;
      }
      const next = (await r.json()) as SessionResult;
      setCurrent(next);
      setShowPw(true);
      onSessionReplaced?.(next);
    } catch (e) {
      setRegenError(String(e));
    } finally {
      setRegenLoading(false);
    }
  };

  const expiresLabel = new Date(current.expires_at).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="surface w-full max-w-2xl overflow-hidden p-0"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between border-b border-slate-200 bg-gradient-to-r from-vju-500 to-vju-700 px-5 py-4 text-white dark:border-slate-700">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest opacity-80">
              Phiên SSH sẵn sàng
            </p>
            <h2 className="text-lg font-bold leading-tight">
              Kit {current.target_user}@{current.target_host}
            </h2>
            <p className="mt-0.5 text-xs opacity-90">Hết slot: {expiresLabel}</p>
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

        <div className="space-y-5 p-5">
          {/* Step 1 — password */}
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              <KeyRound className="mr-1 inline h-3.5 w-3.5" />
              Password (cố định suốt slot)
            </p>
            <div className="flex items-stretch gap-0 overflow-hidden rounded-md border-2 border-emerald-400 bg-slate-900">
              <pre className="flex-1 select-all px-4 py-3 font-mono text-xl font-bold tracking-wider text-emerald-300">
                {showPw ? current.password : "••••-••••-••••"}
              </pre>
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                className="border-l border-slate-700 bg-slate-800 px-3 text-xs font-semibold text-slate-300 hover:bg-slate-700"
              >
                {showPw ? "Ẩn" : "Hiện"}
              </button>
              <button
                type="button"
                onClick={copyPw}
                className="border-l border-slate-700 bg-slate-800 px-4 text-sm font-semibold text-slate-200 hover:bg-slate-700"
              >
                {copiedPw ? "✓ Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-slate-500">
              Password này có hiệu lực đến hết slot — bấm <em>Get SSH access</em>{" "}
              bất cứ lúc nào để xem lại.
              {current.regenerate_count > 0 && (
                <span className="ml-1 text-amber-600 dark:text-amber-400">
                  (đã regenerate {current.regenerate_count} lần)
                </span>
              )}
            </p>
          </div>

          {/* Step 2 — SSH command */}
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              <Terminal className="mr-1 inline h-3.5 w-3.5" />
              Dán lệnh này vào terminal / MobaXterm
            </p>
            <div className="flex items-stretch gap-0 overflow-hidden rounded-md border border-slate-700 bg-slate-900">
              <pre className="flex-1 overflow-x-auto whitespace-pre-wrap break-all px-3 py-2.5 font-mono text-xs text-emerald-300">
                {current.ssh_command}
              </pre>
              <button
                type="button"
                onClick={copyCmd}
                className="border-l border-slate-700 bg-slate-800 px-4 text-sm font-semibold text-slate-200 hover:bg-slate-700"
              >
                {copiedCmd ? "✓ Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-slate-500">
              Gateway:{" "}
              <code className="font-mono">
                {current.ssh_username}@{current.jump_host}:{current.jump_port}
              </code>{" "}
              → KIT{" "}
              <code className="font-mono">
                {current.target_user}@{current.target_host}
              </code>
            </p>
          </div>

          {/* MobaXterm hint */}
          <details className="rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40">
            <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
              Dùng MobaXterm thay vì terminal?
            </summary>
            <div className="space-y-1 px-3 pb-2 text-[11px] text-slate-600 dark:text-slate-300">
              <p>
                Session → SSH → <strong>Remote host</strong>:{" "}
                <code className="font-mono">{current.target_host}</code>{" "}
                · <strong>Username</strong>:{" "}
                <code className="font-mono">{current.target_user}</code>
              </p>
              <p>
                Advanced SSH → Network settings → tick{" "}
                <strong>Connect through SSH gateway (jump host)</strong>:
              </p>
              <p className="pl-4">
                Gateway host:{" "}
                <code className="font-mono">{current.jump_host}</code> · Port:{" "}
                <code className="font-mono">{current.jump_port}</code> · User:{" "}
                <code className="font-mono">{current.ssh_username}</code>
              </p>
              <p>
                Khi connect: nhập password ở trên cho{" "}
                <code className="font-mono">{current.ssh_username}</code>
                @gateway.
              </p>
            </div>
          </details>

          {/* Lifecycle note */}
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-[12px] text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-200">
            <p className="font-semibold">⚡ Khi hết slot ({expiresLabel}):</p>
            <ul className="ml-5 list-disc space-y-0.5 text-[11px]">
              <li>Gateway chặn mọi auth attempt với password này</li>
              <li>
                Phiên đang chạy bị cắt trong vòng 30 giây (có banner cảnh báo
                trước 5 phút)
              </li>
              <li>Audit log lưu lại mọi attempt</li>
            </ul>
          </div>

          {/* Regenerate */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-3 dark:border-slate-700">
            <p className="text-[11px] text-slate-500">
              Password lộ hoặc cần đổi? Bấm để rotate — bản cũ huỷ ngay.
            </p>
            <button
              type="button"
              onClick={regenerate}
              disabled={regenLoading}
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-60 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
            >
              {regenLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Regenerate password
            </button>
          </div>
          {regenError && (
            <p className="text-[11px] text-rose-600">Lỗi: {regenError}</p>
          )}
        </div>
      </div>
    </div>
  );
}
