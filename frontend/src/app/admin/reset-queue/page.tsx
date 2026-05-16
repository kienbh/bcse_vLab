"use client";

import { AlertTriangle, Check, Cpu, Inbox, Loader2, Power, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Status = "pending" | "approved" | "rejected" | "completed" | "failed";

type Request = {
  id: string;
  requester_id: string;
  requester_display: string;
  device_id: string;
  device_name: string;
  booking_id: string | null;
  reason: string;
  status: Status;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  completed_at: string | null;
  auto_approved: boolean;
};

const STATUS_BADGE: Record<Status, string> = {
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  approved: "bg-vju-100 text-vju-700 dark:bg-vju-950/40 dark:text-vju-300",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  failed: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
};

const STATUS_LABEL: Record<Status, string> = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  completed: "Hoàn thành",
  failed: "Lỗi plug",
};

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s trước`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} phút trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m trước`;
  const d = Math.floor(h / 24);
  return `${d} ngày trước`;
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ResetQueueInner() {
  const { user } = useUser();
  const [pending, setPending] = useState<Request[]>([]);
  const [history, setHistory] = useState<Request[]>([]);
  const [loading, setLoading] = useState(true);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pRes, hRes] = await Promise.all([
        fetch(`${API}/reset-requests?status=pending&limit=50`, { credentials: "include" }),
        fetch(`${API}/reset-requests?limit=50`, { credentials: "include" }),
      ]);
      const p = pRes.ok ? await pRes.json() : [];
      const h = hRes.ok ? await hRes.json() : [];
      setPending(p);
      // History = non-pending, sorted by decided_at desc, dedupe with pending
      const pIds = new Set(p.map((x: Request) => x.id));
      setHistory(h.filter((x: Request) => !pIds.has(x.id)).slice(0, 30));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-refresh every 15s
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 15_000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (tick > 0) refresh();
  }, [tick, refresh]);

  // SSE: refresh on reset.requested / reset.queue.updated events
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${API}/events/stream`, { withCredentials: true });
      const onChange = () => refresh();
      es.addEventListener("reset.requested", onChange);
      es.addEventListener("reset.queue.updated", onChange);
      es.addEventListener("reset.decided", onChange);
    } catch {
      /* SSE unsupported, fallback polling above */
    }
    return () => {
      es?.close();
    };
  }, [refresh]);

  const decide = async (id: string, decision: "approve" | "reject", note?: string) => {
    setDecidingId(id);
    try {
      const r = await fetch(`${API}/reset-requests/${id}/${decision}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision_note: note ?? null }),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        alert(`Không xử lý được: ${data?.detail?.code ?? r.status}`);
      }
      await refresh();
    } finally {
      setDecidingId(null);
    }
  };

  const approve = (id: string) => decide(id, "approve");

  /**
   * Pilot reality: the plug API isn't online in Hoà Lạc, so "Duyệt + Reset"
   * just marks the request approved without actually cycling power. After
   * the admin physically flips the rocker, they click "Đã reset xong (tay)"
   * → flips device.power_state to ON + closes any pending+approved requests
   * for that device. All bundled in one POST /api/admin/devices/{id}/mark-reset-done.
   */
  const markDone = async (deviceId: string, deviceName: string) => {
    if (
      !confirm(
        `Xác nhận đã cắm điện lại cho ${deviceName}? Việc này sẽ:\n` +
          "  • Đặt nguồn điện = ON\n" +
          "  • Đóng mọi yêu cầu reset đang chờ cho thiết bị này",
      )
    )
      return;
    setDecidingId(deviceId);
    try {
      const r = await fetch(`${API}/admin/devices/${deviceId}/mark-reset-done`, {
        method: "POST",
        credentials: "include",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert(`Không xử lý được: ${data?.detail?.code ?? r.status}`);
        return;
      }
      refresh();
    } finally {
      setDecidingId(null);
    }
  };

  const reject = async (id: string) => {
    const note = window.prompt("Lý do từ chối (sẽ gửi cho người yêu cầu):", "");
    if (note === null) return;
    await decide(id, "reject", note.trim() || undefined);
  };

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="surface flex items-center gap-3 p-6 text-sm">
          <AlertTriangle className="h-5 w-5 text-amber-500" />
          <p>Trang này chỉ dành cho lecturer / admin.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <AdminPageHeader
        title="Hàng chờ reset thiết bị"
        subtitle={
          <>
            <span className="font-semibold text-amber-700 dark:text-amber-300">{pending.length}</span>{" "}
            yêu cầu chờ duyệt · auto-refresh 15s
          </>
        }
        actions={
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Làm mới
          </button>
        }
      />

      {error && (
        <div className="surface border-rose-300 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30">
          {error}
        </div>
      )}

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">
          <span className="relative inline-flex h-2 w-2">
            {pending.length > 0 && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
            )}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${pending.length > 0 ? "bg-amber-500" : "bg-slate-400"}`} />
          </span>
          Đang chờ duyệt ({pending.length})
        </h2>
        {pending.length === 0 ? (
          <div className="surface flex flex-col items-center gap-3 p-10 text-center text-slate-500">
            <Inbox className="h-10 w-10 text-slate-300" />
            <p className="text-sm">Không có yêu cầu chờ duyệt.</p>
          </div>
        ) : (
          <ul className="space-y-3">
            {pending.map((r) => (
              <li key={r.id} className="surface flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
                <div className="flex items-start gap-4">
                  <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-600 text-white shadow-sm">
                    <Cpu className="h-5 w-5" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-base font-semibold">
                      <span className="font-mono">{r.requester_display}</span>
                      <span className="text-slate-400 mx-2">·</span>
                      <span className="font-mono text-vju-700 dark:text-vju-300">{r.device_name}</span>
                    </p>
                    <p className="text-sm text-slate-700 dark:text-slate-300">
                      Lý do: <span className="italic">{r.reason}</span>
                    </p>
                    <p className="text-xs text-slate-500">
                      {timeAgo(r.requested_at)} · {fmt(r.requested_at)}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={decidingId === r.id}
                    onClick={() => approve(r.id)}
                    className="inline-flex items-center gap-1 rounded-md bg-emerald-500 px-3 py-2 text-sm font-bold text-white hover:bg-emerald-600 disabled:opacity-50"
                  >
                    {decidingId === r.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    Duyệt + Reset
                  </button>
                  <button
                    type="button"
                    disabled={decidingId === r.id}
                    onClick={() => markDone(r.device_id, r.device_name)}
                    title="Mình đã ra Hoà Lạc rút/cắm điện xong → đóng request + set nguồn = ON"
                    className="inline-flex items-center gap-1 rounded-md bg-amber-500 px-3 py-2 text-sm font-bold text-white hover:bg-amber-600 disabled:opacity-50"
                  >
                    <Power className="h-4 w-4" />
                    Đã reset xong (tay)
                  </button>
                  <button
                    type="button"
                    disabled={decidingId === r.id}
                    onClick={() => reject(r.id)}
                    className="inline-flex items-center gap-1 rounded-md border border-rose-300 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-700 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
                  >
                    <X className="h-4 w-4" />
                    Từ chối
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">
          Lịch sử gần đây ({history.length})
        </h2>
        {history.length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có yêu cầu nào.</p>
        ) : (
          <ul className="space-y-2">
            {history.map((r) => (
              <li key={r.id} className="surface flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs">{r.requester_display}</span>
                  <span className="text-slate-400">→</span>
                  <span className="font-mono text-xs text-vju-700 dark:text-vju-300">{r.device_name}</span>
                  <span className="text-xs italic text-slate-500 max-w-xs truncate">{r.reason}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  {r.auto_approved && (
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                      AUTO
                    </span>
                  )}
                  <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${STATUS_BADGE[r.status]}`}>
                    {STATUS_LABEL[r.status]}
                  </span>
                  <span className="text-slate-400">{fmt(r.decided_at ?? r.requested_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default function ResetQueuePage() {
  return (
    <AuthGate>
      <ResetQueueInner />
    </AuthGate>
  );
}
