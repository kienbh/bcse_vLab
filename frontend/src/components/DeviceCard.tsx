"use client";

import {
  Activity,
  Calendar,
  Loader2,
  Power,
  Radio,
  Sparkles,
  Terminal,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type DeviceFamily = "fpga" | "jetson" | "rpi" | "vps";

export type PowerState = "on" | "off" | "resetting";

export type Device = {
  id: string;
  name: string;
  device_type:
    | "fpga_kv260"
    | "jetson_nano"
    | "jetson_orin"
    | "rpi4"
    | "rpi5"
    | "vps";
  model: string;
  status: "available" | "in_use" | "maintenance" | "offline";
  power_state: PowerState;
  capabilities: Record<string, unknown>;
};

/**
 * Highlight the trailing number group of a device slug, e.g. "fpga-kv260-001"
 * → ("fpga-kv260-", "001"). Used by the card header to make "kit số mấy"
 * instantly readable across the 3×3 grid.
 */
function splitDeviceNumber(name: string): { prefix: string; number: string | null } {
  const m = name.match(/^(.*?[-_])(\d{1,4})$/);
  if (m) return { prefix: m[1], number: m[2] };
  return { prefix: name, number: null };
}

const POWER_BADGE: Record<PowerState, { label: string; dot: string; text: string }> = {
  on: {
    label: "Nguồn bật",
    dot: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.85)]",
    text: "text-emerald-100",
  },
  off: {
    label: "Đã tắt",
    dot: "bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.75)]",
    text: "text-rose-100",
  },
  resetting: {
    label: "Đang reset",
    dot: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.85)] animate-pulse",
    text: "text-amber-100",
  },
};

/** Pretty-print a capability value (boolean / number / string / object / array). */
function formatCapValue(v: unknown): string {
  if (v === true) return "✓";
  if (v === false) return "✗";
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.map(String).join(", ");
  return JSON.stringify(v);
}

export type LiveStatus = {
  device_id: string;
  checked_at: string;
  ssh_host: string;
  ssh_port: number;
  reachable: boolean;
  latency_ms: number | null;
  db_status: Device["status"];
  current_booking: {
    booking_id: string;
    user_name: string;
    user_email: string | null;
    student_code: string | null;
    start_time: string;
    end_time: string;
  } | null;
  is_my_booking: boolean;
  next_booking: { start_time: string; end_time: string } | null;
  has_plug: boolean;
};

type DerivedState = "available" | "occupied" | "offline" | "maintenance";

function deriveState(d: Device, live: LiveStatus | null): DerivedState {
  if (d.status === "maintenance") return "maintenance";
  if (live && !live.reachable) return "offline";
  if (d.status === "offline" && !live?.reachable) return "offline";
  if (live?.current_booking) return "occupied";
  if (d.status === "in_use") return "occupied";
  return "available";
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

function remainingMs(endIso: string): number {
  return new Date(endIso).getTime() - Date.now();
}

function fmtRemaining(ms: number): string {
  if (ms <= 0) return "đã hết";
  const totalMin = Math.floor(ms / 60_000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h <= 0) return `${m} phút`;
  return `${h}h ${m.toString().padStart(2, "0")}m`;
}

export type FamilyTheme = {
  badge: string;
  accent: string;
  available: string;
  occupied: string;
  offline: string;
  maintenance: string;
};

// Per-family color theme. `available` follows the family's signature color
// (matches the family page header on /devices/{family}), so cards on the FPGA
// page read blue, Jetson reads green, RPi reads pink — no more visual mismatch
// between the page banner and the card banner. `occupied/offline/maintenance`
// stay neutral across all families to avoid hiding warning states behind a
// theme-matched green.
const THEMES: Record<DeviceFamily, FamilyTheme> = {
  fpga: {
    badge: "FPGA",
    accent: "from-vju-500 to-vju-700",
    available:
      "from-vju-400 via-vju-500 to-vju-700 shadow-vju-500/30",
    occupied:
      "from-amber-400 via-orange-500 to-amber-600 shadow-amber-500/30",
    offline:
      "from-slate-400 via-slate-500 to-slate-700 shadow-slate-500/20",
    maintenance:
      "from-zinc-400 via-zinc-500 to-zinc-600 shadow-zinc-500/20",
  },
  jetson: {
    badge: "JETSON",
    accent: "from-emerald-500 to-teal-700",
    available:
      "from-emerald-400 via-emerald-500 to-teal-600 shadow-emerald-500/30",
    occupied:
      "from-amber-400 via-orange-500 to-amber-600 shadow-amber-500/30",
    offline:
      "from-slate-400 via-slate-500 to-slate-700 shadow-slate-500/20",
    maintenance:
      "from-zinc-400 via-zinc-500 to-zinc-600 shadow-zinc-500/20",
  },
  rpi: {
    badge: "RPI",
    accent: "from-rose-500 to-pink-700",
    available:
      "from-rose-400 via-rose-500 to-pink-600 shadow-rose-500/30",
    occupied:
      "from-amber-400 via-orange-500 to-amber-600 shadow-amber-500/30",
    offline:
      "from-slate-400 via-slate-500 to-slate-700 shadow-slate-500/20",
    maintenance:
      "from-zinc-400 via-zinc-500 to-zinc-600 shadow-zinc-500/20",
  },
  vps: {
    badge: "VPS",
    accent: "from-indigo-500 to-indigo-700",
    available:
      "from-indigo-400 via-indigo-500 to-indigo-700 shadow-indigo-500/30",
    occupied:
      "from-amber-400 via-orange-500 to-amber-600 shadow-amber-500/30",
    offline:
      "from-slate-400 via-slate-500 to-slate-700 shadow-slate-500/20",
    maintenance:
      "from-zinc-400 via-zinc-500 to-zinc-600 shadow-zinc-500/20",
  },
};

const STATE_LABEL: Record<DerivedState, { vi: string; subtitle: string }> = {
  available: { vi: "Đang trống", subtitle: "Sẵn sàng — bấm để đặt ngay" },
  occupied: { vi: "Đang được dùng", subtitle: "Bị nhóm khác chiếm slot" },
  offline: { vi: "Mất kết nối", subtitle: "Không ping được SSH" },
  maintenance: { vi: "Bảo trì", subtitle: "Admin đang bảo trì kit" },
};

export interface DeviceCardProps {
  device: Device;
  family: DeviceFamily;
  onBook: (device: Device) => void;
  onConnect?: (device: Device, bookingId: string) => void;
}

export function DeviceCard({ device, family, onBook, onConnect }: DeviceCardProps) {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // re-render every 30s for countdown

  const poll = useCallback(async () => {
    try {
      const r = await fetch(`${API}/devices/${device.id}/live-status`, {
        credentials: "include",
        cache: "no-store",
      });
      if (r.ok) {
        setLive(await r.json());
        setError(null);
      } else {
        setError(`HTTP ${r.status}`);
      }
    } catch (e) {
      setError(String(e));
    }
  }, [device.id]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 8000);
    return () => clearInterval(id);
  }, [poll]);

  // Tick every 30s so the "X phút còn lại" countdown updates live
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const state = deriveState(device, live);
  const theme = THEMES[family];
  const gradient = theme[state];

  const resetPlug = async () => {
    const reason = window.prompt(
      `Lý do reset ${device.name}?\n(VD: kit treo sau khi nạp bitstream, ssh không phản hồi...)`,
      "",
    );
    if (reason === null) return;
    const trimmed = reason.trim();
    if (trimmed.length < 3) {
      setResetMsg("× Cần ghi rõ lý do (≥ 3 ký tự).");
      return;
    }
    setResetting(true);
    setResetMsg(null);
    try {
      const r = await fetch(`${API}/reset-requests`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: device.id, reason: trimmed }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        if (data.auto_approved) {
          setResetMsg("✓ Đã auto-reset (bạn là người đang dùng kit).");
          setTimeout(poll, 1500);
        } else {
          setResetMsg("📨 Đã gửi yêu cầu. Đang đợi GV/admin duyệt...");
        }
      } else {
        const code = data?.detail?.code ?? "ERROR";
        setResetMsg(
          code === "REQUEST_ALREADY_PENDING"
            ? "⏳ Đã có 1 yêu cầu reset đang chờ duyệt cho kit này."
            : code === "ACCESS_DENIED"
              ? "× Bạn chưa được cấp quyền cho kit này."
              : code === "DEVICE_NOT_FOUND"
                ? "× Không tìm thấy thiết bị."
                : `× Lỗi: ${code}`,
        );
      }
    } catch (e) {
      setResetMsg(`× ${String(e)}`);
    } finally {
      setResetting(false);
    }
  };

  const isOwner = live?.is_my_booking ?? false;
  const current = live?.current_booking;
  const remainingForOwner =
    isOwner && current ? fmtRemaining(remainingMs(current.end_time)) : null;
  void tick;

  const { prefix, number } = splitDeviceNumber(device.name);
  const power = POWER_BADGE[device.power_state];

  return (
    <div className="surface relative flex flex-col overflow-hidden p-0">
      {/* Big gradient banner shows state at a glance */}
      <div
        className={`relative bg-gradient-to-br ${gradient} px-5 py-4 text-white shadow-md transition`}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest opacity-80">
              {theme.badge}
            </p>
            <p className="mt-1 leading-none">
              <span className="font-mono text-sm font-semibold opacity-75">
                {prefix.toUpperCase()}
              </span>
              {number && (
                <span className="ml-0.5 font-mono text-3xl font-extrabold tracking-tight drop-shadow">
                  {number}
                </span>
              )}
              {!number && (
                <span className="font-mono text-base font-bold">
                  {device.name.toUpperCase()}
                </span>
              )}
            </p>
            <p className="mt-1.5 text-sm font-semibold leading-tight">
              {device.model}
            </p>
            {/* Power LED indicator — admin manually toggles in /admin/devices */}
            <p
              className={`mt-1.5 inline-flex items-center gap-1.5 text-[11px] font-semibold ${power.text}`}
            >
              <span className={`h-2 w-2 rounded-full ${power.dot}`} />
              {power.label}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span
              className={`flex items-center gap-1 rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-bold uppercase backdrop-blur-sm ${
                live === null
                  ? "opacity-50"
                  : live.reachable
                    ? ""
                    : "bg-rose-500/50"
              }`}
            >
              {live === null ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : live.reachable ? (
                <Wifi className="h-3 w-3" />
              ) : (
                <WifiOff className="h-3 w-3" />
              )}
              {live?.latency_ms != null
                ? `${live.latency_ms.toFixed(0)}ms`
                : live?.reachable
                  ? "ok"
                  : "—"}
            </span>
            {live && (
              <span className="font-mono text-[10px] opacity-70">
                {live.ssh_host}
              </span>
            )}
          </div>
        </div>

        <div className="mt-3">
          <p className="text-2xl font-extrabold tracking-tight">
            {STATE_LABEL[state].vi}
          </p>
          <p className="text-xs opacity-90">{STATE_LABEL[state].subtitle}</p>
        </div>
      </div>

      <div className="flex flex-col gap-3 p-5">
        {/* Live ssh probe line */}
        <div
          className="flex items-center justify-between rounded-md bg-slate-100 px-3 py-1.5 font-mono text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300"
          title={
            error
              ? "Backend không trả /api/devices/{id}/live-status — vấn đề ở portal, không phải kit"
              : live?.reachable
                ? "Backend ping SSH thành công"
                : "Backend ping SSH timeout — kit có thể đang đơ"
          }
        >
          <span className="inline-flex items-center gap-1.5">
            <Radio
              className={`h-3 w-3 ${
                error
                  ? "text-amber-500"
                  : live?.reachable
                    ? "text-emerald-500"
                    : "text-rose-500"
              }`}
            />
            ssh {device.name}
          </span>
          <span className="text-slate-400">
            {error
              ? "API lỗi"
              : live?.reachable
                ? `${live.latency_ms?.toFixed(0) ?? "?"}ms · port ${live.ssh_port}`
                : live === null
                  ? "checking..."
                  : "kit không phản hồi"}
          </span>
        </div>

        {/* Occupied panel — who has it + remaining time */}
        {state === "occupied" && current && (
          <div className="space-y-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs dark:border-amber-900/50 dark:bg-amber-950/30">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-amber-800 dark:text-amber-200">
                {isOwner ? "Bạn đang chiếm slot" : current.user_name}
              </span>
              <span className="font-mono text-amber-700 dark:text-amber-300">
                {fmtTime(current.start_time)}–{fmtTime(current.end_time)}
              </span>
            </div>
            {isOwner && remainingForOwner && (
              <p className="text-[11px] text-amber-700 dark:text-amber-300">
                ⏱ Còn lại <strong>{remainingForOwner}</strong>
              </p>
            )}
            {!isOwner && current.student_code && (
              <p className="font-mono text-[11px] text-amber-700 dark:text-amber-300">
                {current.student_code}
              </p>
            )}
          </div>
        )}

        {/* Next-slot hint when card is available */}
        {state === "available" && live?.next_booking && (
          <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs dark:border-slate-800 dark:bg-slate-900/50">
            <p className="text-slate-500 dark:text-slate-400">
              <Calendar className="mr-1 inline h-3 w-3" />
              Slot tiếp theo: <strong className="text-slate-700 dark:text-slate-200">
                {fmtDate(live.next_booking.start_time)} {fmtTime(live.next_booking.start_time)}
              </strong>
            </p>
          </div>
        )}

        {/* Capability key:value chips — show actual specs, not just keys */}
        {Object.keys(device.capabilities).length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(device.capabilities)
              .slice(0, 6)
              .map(([k, v]) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                >
                  <span className="text-slate-400">{k}</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    {formatCapValue(v)}
                  </span>
                </span>
              ))}
          </div>
        ) : (
          <p className="text-[10px] italic text-slate-400 dark:text-slate-500">
            Chưa khai báo thông số. Admin có thể bổ sung trong /admin/devices.
          </p>
        )}

        {/* Actions */}
        <div className="mt-1 flex flex-col gap-2">
          {state === "available" && (
            <button
              type="button"
              onClick={() => onBook(device)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-amber-500 to-orange-600 px-4 py-3 text-sm font-bold text-white shadow-md transition hover:shadow-lg hover:brightness-110 active:scale-[0.98]"
            >
              <Sparkles className="h-4 w-4" />
              ĐẶT SLOT NGAY
            </button>
          )}

          {state === "occupied" && !isOwner && (
            <button
              type="button"
              disabled
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            >
              Kit đang được sử dụng
            </button>
          )}

          {state === "occupied" && isOwner && (
            <>
              {onConnect && current && (
                <button
                  type="button"
                  onClick={() => onConnect(device, current.booking_id)}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-vju-500 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-vju-600"
                >
                  <Terminal className="h-4 w-4" />
                  Mở terminal SSH
                </button>
              )}
              <button
                type="button"
                onClick={resetPlug}
                disabled={resetting}
                title={
                  live?.has_plug
                    ? "Gửi yêu cầu reset tới GV/admin (auto-approve nếu bạn đang dùng kit)"
                    : "Kit chưa gán smart plug — vẫn có thể yêu cầu, GV/admin sẽ xử lý thủ công"
                }
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-700 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
              >
                {resetting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Power className="h-4 w-4" />
                )}
                Yêu cầu reset
              </button>
            </>
          )}

          {state === "offline" && (
            <>
              <button
                type="button"
                disabled
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
              >
                <WifiOff className="h-4 w-4" />
                Kit không phản hồi
              </button>
              {/* Reset chỉ hiện khi user là người đang chiếm slot — tránh
                  user random spam reset cho kit không liên quan. Backend
                  cũng kiểm tra quyền nhưng UI cần tighten lên cùng. */}
              {isOwner && (
                <button
                  type="button"
                  onClick={resetPlug}
                  disabled={resetting}
                  title="Bạn đang có slot active — auto-approve sau khi gửi"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-700 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
                >
                  {resetting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Power className="h-4 w-4" />
                  )}
                  Yêu cầu reset kit đơ
                </button>
              )}
            </>
          )}

          {state === "maintenance" && (
            <button
              type="button"
              disabled
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            >
              <Activity className="h-4 w-4" />
              Đang bảo trì
            </button>
          )}

          {resetMsg && (
            <p
              className={`text-[11px] ${
                resetMsg.startsWith("✓")
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-rose-600 dark:text-rose-400"
              }`}
            >
              {resetMsg}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
