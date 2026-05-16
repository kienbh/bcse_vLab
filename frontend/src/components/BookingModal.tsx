"use client";

import { Calendar, Loader2, Sparkles, Clock, X, KeyRound } from "lucide-react";
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
          msg: "✓ Đặt lịch thành công. Đến giờ vào Bookings → Connect để mở terminal.",
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

export interface SessionResult {
  session_id: string;
  booking_id?: string;
  ssh_user: string;        // user trên FPGA (ubuntu)
  ssh_host: string;        // IP nội bộ FPGA (192.168.2.93)
  ssh_port: number;
  private_key: string;
  fingerprint: string;
  // ProxyJump endpoint (M5.7)
  jump_user?: string;      // sess-abc123 — dynamic user trên SV14
  jump_host?: string;      // ssh.bcse-vju.com
  jump_port?: number;      // 2222
  ssh_command?: string;    // lệnh hoàn chỉnh có sẵn -i -J
  jump_user_ready?: boolean;
  expires_at?: string;
  mocked: boolean;
}

export interface SessionLaunchModalProps {
  session: SessionResult;
  onClose: () => void;
}

export function SessionLaunchModal({ session, onClose }: SessionLaunchModalProps) {
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);

  const cmd =
    session.ssh_command ??
    `ssh -i vju-session.key -p ${session.ssh_port} ${session.ssh_user}@${session.ssh_host}`;

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(session.private_key);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 1800);
    } catch { /* ignore */ }
  };
  const copyCmd = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopiedCmd(true);
      setTimeout(() => setCopiedCmd(false), 1800);
    } catch { /* ignore */ }
  };
  const downloadKey = () => {
    const blob = new Blob([session.private_key], { type: "application/x-pem-file" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "vju-session.key";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const expiresLabel = session.expires_at
    ? new Date(session.expires_at).toLocaleTimeString("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

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
              Session sẵn sàng {session.mocked && "(mock)"}
            </p>
            <h2 className="text-lg font-bold leading-tight">
              SSH qua gateway · {session.ssh_user}@{session.ssh_host}
            </h2>
            {expiresLabel && (
              <p className="mt-0.5 text-xs opacity-90">Hết slot: {expiresLabel}</p>
            )}
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
          {/* Step 1 — private key */}
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              Bước 1 · Lưu private key vào máy
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={downloadKey}
                className="inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-emerald-500 to-teal-600 px-4 py-2 text-sm font-bold text-white shadow hover:shadow-lg"
              >
                <KeyRound className="h-4 w-4" />
                Tải vju-session.key
              </button>
              <button
                type="button"
                onClick={copyKey}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                {copiedKey ? "✓ Copied" : "Copy nội dung key"}
              </button>
            </div>
            <p className="mt-1.5 text-[10px] text-slate-500">
              Linux/Mac: <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">chmod 600 vju-session.key</code>
              {" · "}Windows PowerShell:{" "}
              <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">icacls vju-session.key /inheritance:r /grant:r &quot;${"{env:USERNAME}"}:R&quot;</code>
            </p>
          </div>

          {/* Step 2 — SSH command with ProxyJump */}
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              Bước 2 · Lệnh SSH (paste vào MobaXterm / PowerShell)
            </p>
            <div className="flex items-stretch gap-0 overflow-hidden rounded-md border border-slate-700 bg-slate-900">
              <pre className="flex-1 overflow-x-auto whitespace-pre-wrap break-all px-3 py-2.5 font-mono text-xs text-emerald-300">
                {cmd}
              </pre>
              <button
                type="button"
                onClick={copyCmd}
                className="border-l border-slate-700 bg-slate-800 px-4 text-sm font-semibold text-slate-200 hover:bg-slate-700"
              >
                {copiedCmd ? "✓ Copied" : "Copy"}
              </button>
            </div>
            {session.jump_user && (
              <p className="mt-1.5 text-[11px] text-slate-500">
                Gateway:{" "}
                <code className="font-mono">
                  {session.jump_user}@{session.jump_host}:{session.jump_port}
                </code>
                {" → "}
                <code className="font-mono">
                  {session.ssh_user}@{session.ssh_host}
                </code>
              </p>
            )}
          </div>

          {/* Lifecycle note */}
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-[12px] text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-200">
            <p className="font-semibold">⚡ Hết slot:</p>
            <ul className="ml-5 list-disc space-y-0.5 text-[11px]">
              <li>
                Gateway SV14 xóa user{" "}
                <code className="font-mono">{session.jump_user ?? "session"}</code>
              </li>
              <li>Mọi nỗ lực reconnect đều fail tại tầng gateway</li>
              <li>Audit log lưu lại toàn bộ phiên</li>
            </ul>
          </div>

          <details className="rounded-md border border-slate-200 dark:border-slate-700">
            <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
              <KeyRound className="mr-1 inline h-3 w-3" />
              Xem private key text (nếu không tải được file)
            </summary>
            <textarea
              readOnly
              value={session.private_key}
              rows={8}
              onFocus={(e) => e.currentTarget.select()}
              className="block w-full border-0 bg-slate-900 px-3 py-2 font-mono text-[10px] text-emerald-300"
            />
            <p className="px-3 py-1 text-[10px] text-slate-500">
              Fingerprint: <code className="font-mono">{session.fingerprint}</code>
            </p>
          </details>
        </div>
      </div>
    </div>
  );
}


