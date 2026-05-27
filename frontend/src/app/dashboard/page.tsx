"use client";

import Link from "next/link";
import {
  Calendar,
  CalendarDays,
  Cpu,
  Cog,
  Clock,
  Loader2,
  Mail,
  Server,
  Terminal,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { Countdown } from "@/components/Countdown";
import { SessionLaunchModal, SessionResult } from "@/components/BookingModal";
import { QuotaWidget } from "@/components/QuotaWidget";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Booking = {
  id: string;
  device_id: string;
  start_time: string;
  end_time: string;
  status: string;
  granted_via: string;
};

type Device = {
  id: string;
  name: string;
  device_type: string;
  model: string;
};

type Grant = {
  id: string;
  device_id: string;
  valid_from: string;
  valid_to: string;
  reason: string;
  revoked_at: string | null;
  device_name: string | null;
};

type AccessRequest = {
  id: string;
  device_id: string;
  requested_from: string;
  requested_to: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  device_name: string | null;
  created_at: string;
};

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function DashboardInner() {
  const { user } = useUser();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [devices, setDevices] = useState<Map<string, Device>>(new Map());
  const [grants, setGrants] = useState<Grant[]>([]);
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<{ data: SessionResult; bookingId: string } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [b, d, g, r] = await Promise.all([
        fetch(`${API}/bookings`, { credentials: "include" }).then((x) => (x.ok ? x.json() : [])),
        fetch(`${API}/devices`, { credentials: "include" }).then((x) => (x.ok ? x.json() : [])),
        fetch(`${API}/vps-access/grants/mine`, { credentials: "include" }).then((x) =>
          x.ok ? x.json() : [],
        ),
        fetch(`${API}/vps-access/requests/mine`, { credentials: "include" }).then((x) =>
          x.ok ? x.json() : [],
        ),
      ]);
      setBookings(b as Booking[]);
      setDevices(new Map((d as Device[]).map((x) => [x.id, x])));
      setGrants(g as Grant[]);
      setRequests(r as AccessRequest[]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const connectBooking = async (bookingId: string) => {
    const r = await fetch(`${API}/bookings/${bookingId}/access`, {
      method: "POST",
      credentials: "include",
    });
    if (r.ok) {
      const data = (await r.json()) as SessionResult;
      setSession({ data, bookingId });
    } else {
      const e = await r.json().catch(() => ({}));
      alert(`Không kết nối được: ${e?.detail?.code ?? r.status}`);
    }
  };

  if (!user) return null;

  const now = Date.now();
  // Active grants (long-term, lecturer-granted VPS access)
  const activeGrants = grants.filter(
    (g) =>
      !g.revoked_at &&
      new Date(g.valid_from).getTime() <= now &&
      new Date(g.valid_to).getTime() >= now,
  );
  // SV's currently-running auto block (if any)
  const liveAutoBlock = bookings.find(
    (b) =>
      b.granted_via === "auto" &&
      (b.status === "scheduled" || b.status === "active") &&
      new Date(b.start_time).getTime() <= now &&
      new Date(b.end_time).getTime() > now,
  );
  // SV's future auto block (scheduled but not started yet)
  const upcomingAutoBlock = bookings.find(
    (b) =>
      b.granted_via === "auto" &&
      (b.status === "scheduled" || b.status === "active") &&
      new Date(b.start_time).getTime() > now,
  );
  // Pending VPS proposals
  const pendingProposals = requests.filter((r) => r.status === "pending");
  // Kit bookings (non-auto, non-special_access) — upcoming or active
  const kitBookings = bookings
    .filter((b) => {
      if (b.granted_via === "auto" || b.granted_via === "special_access") return false;
      if (b.status === "cancelled" || b.status === "completed") return false;
      const dev = devices.get(b.device_id);
      return dev?.device_type !== "vps";
    })
    .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime())
    .slice(0, 5);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      {/* Greeting */}
      <header>
        <h1 className="text-3xl font-bold tracking-tight">
          Xin chào, {user.full_name?.split(" ").slice(-1)[0] || user.email}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {user.email}
          {user.student_code && (
            <>
              {" · "}
              <span className="font-mono">{user.student_code}</span>
            </>
          )}
        </p>
      </header>

      {loading ? (
        <div className="surface flex items-center gap-2 p-8 text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải...
        </div>
      ) : (
        <>
          {/* === ACCESS — what can I SSH into NOW? === */}
          <section className="surface overflow-hidden">
            <header className="flex items-center justify-between border-b border-slate-200 bg-gradient-to-r from-indigo-500 to-indigo-700 px-5 py-3 text-white dark:border-slate-800">
              <h2 className="flex items-center gap-2 text-sm font-bold">
                <Terminal className="h-4 w-4" />
                Quyền truy cập đang có
              </h2>
              <span className="text-xs opacity-85">
                {activeGrants.length + (liveAutoBlock ? 1 : 0)} đang chạy
              </span>
            </header>
            <div className="divide-y divide-slate-200 dark:divide-slate-800">
              {/* Live auto block */}
              {liveAutoBlock && (
                <AccessRow
                  icon={<Server className="h-5 w-5 text-indigo-500" />}
                  title={devices.get(liveAutoBlock.device_id)?.name || liveAutoBlock.device_id}
                  subtitle={
                    <>
                      Block auto · {fmtTime(liveAutoBlock.start_time)}–
                      {fmtTime(liveAutoBlock.end_time)}
                    </>
                  }
                  meta={<Countdown start={liveAutoBlock.start_time} end={liveAutoBlock.end_time} compact />}
                  action={
                    <button
                      type="button"
                      onClick={() => connectBooking(liveAutoBlock.id)}
                      className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700"
                    >
                      <Terminal className="h-3 w-3" />
                      SSH
                    </button>
                  }
                />
              )}
              {/* Long grants */}
              {activeGrants.map((g) => {
                const daysLeft = Math.ceil(
                  (new Date(g.valid_to).getTime() - now) / 86_400_000,
                );
                return (
                  <AccessRow
                    key={g.id}
                    icon={<Zap className="h-5 w-5 text-violet-500" />}
                    title={g.device_name || g.device_id}
                    subtitle={<>Grant GV · còn {daysLeft} ngày · &ldquo;{g.reason.slice(0, 50)}&rdquo;</>}
                    meta={
                      <span className="rounded bg-violet-100 px-2 py-0.5 text-[10px] font-bold uppercase text-violet-700 dark:bg-violet-900/40 dark:text-violet-200">
                        grant
                      </span>
                    }
                    action={
                      <button
                        type="button"
                        onClick={async () => {
                          const r = await fetch(`${API}/vps-access/${g.device_id}/access`, {
                            method: "POST",
                            credentials: "include",
                          });
                          if (r.ok) {
                            const data = (await r.json()) as SessionResult;
                            setSession({ data, bookingId: data.booking_id });
                          }
                        }}
                        className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700"
                      >
                        <Terminal className="h-3 w-3" />
                        SSH
                      </button>
                    }
                  />
                );
              })}
              {!liveAutoBlock && activeGrants.length === 0 && (
                <div className="p-5 text-center text-sm text-slate-500">
                  Hiện chưa có quyền nào đang chạy. Đặt block VPS hoặc slot kit ở dưới.
                </div>
              )}
            </div>
          </section>

          {/* === Quick actions === */}
          <div className="grid gap-4 md:grid-cols-3">
            <Link
              href="/devices/vps"
              className="surface flex items-start gap-3 p-4 transition hover:border-indigo-300 hover:shadow-md"
            >
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-700 text-white shadow-sm">
                <Server className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-bold">Đặt block VPS</p>
                <p className="text-xs text-slate-500">
                  6h/block · auto · còn slot là vào
                </p>
              </div>
            </Link>
            <Link
              href="/devices/fpga"
              className="surface flex items-start gap-3 p-4 transition hover:border-vju-300 hover:shadow-md"
            >
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-vju-500 to-vju-700 text-white shadow-sm">
                <Cog className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-bold">Đặt slot kit</p>
                <p className="text-xs text-slate-500">
                  FPGA / Jetson / Pi · slot 1–8h
                </p>
              </div>
            </Link>
            <Link
              href="/vps-access"
              className="surface flex items-start gap-3 p-4 transition hover:border-violet-300 hover:shadow-md"
            >
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-violet-700 text-white shadow-sm">
                <Mail className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-bold">Soạn proposal</p>
                <p className="text-xs text-slate-500">
                  Cần VPS dài hơn 24h → xin grant
                </p>
              </div>
            </Link>
          </div>

          {/* === Upcoming auto block (future) === */}
          {upcomingAutoBlock && !liveAutoBlock && (
            <section className="surface border-l-4 border-l-amber-500 bg-amber-50/60 p-4 dark:bg-amber-950/20">
              <div className="flex items-center gap-3">
                <CalendarDays className="h-5 w-5 text-amber-600" />
                <div className="flex-1">
                  <p className="font-bold">
                    Bạn đã giữ chỗ:{" "}
                    {devices.get(upcomingAutoBlock.device_id)?.name || upcomingAutoBlock.device_id}
                  </p>
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    Bắt đầu {fmtDateTime(upcomingAutoBlock.start_time)} — kết thúc{" "}
                    {fmtTime(upcomingAutoBlock.end_time)}
                  </p>
                </div>
                <Countdown start={upcomingAutoBlock.start_time} end={upcomingAutoBlock.end_time} compact />
              </div>
            </section>
          )}

          {/* === Pending proposals === */}
          {pendingProposals.length > 0 && (
            <section className="surface overflow-hidden">
              <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
                <h2 className="flex items-center gap-2 text-sm font-bold">
                  <Mail className="h-4 w-4 text-amber-500" />
                  Proposal chờ GV duyệt
                </h2>
                <Link href="/vps-access" className="text-xs font-semibold text-vju-500 hover:underline">
                  Xem tất cả →
                </Link>
              </header>
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {pendingProposals.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                    <Mail className="h-4 w-4 text-amber-500" />
                    <div className="flex-1">
                      <p className="font-semibold">{r.device_name}</p>
                      <p className="text-xs text-slate-500">
                        Gửi {fmtDateTime(r.created_at)} · &ldquo;{r.reason.slice(0, 80)}&rdquo;
                      </p>
                    </div>
                    <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-bold uppercase text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                      chờ duyệt
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* === Quota === */}
          <QuotaWidget />

          {/* === Upcoming kit bookings === */}
          <section className="surface overflow-hidden">
            <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
              <h2 className="flex items-center gap-2 text-sm font-bold">
                <Calendar className="h-4 w-4 text-vju-500" />
                Slot kit sắp tới
              </h2>
              <Link href="/bookings" className="text-xs font-semibold text-vju-500 hover:underline">
                Xem tất cả →
              </Link>
            </header>
            {kitBookings.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">
                Chưa có slot kit nào. Đặt ở{" "}
                <Link href="/devices/fpga" className="font-semibold text-vju-500 hover:underline">
                  /devices/fpga
                </Link>{" "}
                hoặc <Link href="/devices/jetson" className="font-semibold text-vju-500 hover:underline">
                  jetson
                </Link>
                /<Link href="/devices/rpi" className="font-semibold text-vju-500 hover:underline">
                  pi
                </Link>
                .
              </p>
            ) : (
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {kitBookings.map((b) => {
                  const dev = devices.get(b.device_id);
                  const startMs = new Date(b.start_time).getTime();
                  const endMs = new Date(b.end_time).getTime();
                  const canConnect =
                    (b.status === "scheduled" || b.status === "active") &&
                    now >= startMs &&
                    now < endMs;
                  return (
                    <li key={b.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                      <Cpu className="h-4 w-4 text-vju-500" />
                      <div className="flex-1">
                        <p className="font-mono text-xs uppercase text-slate-500">
                          {dev?.name ?? b.device_id}
                        </p>
                        <p className="font-semibold">{dev?.model ?? "—"}</p>
                        <p className="text-xs text-slate-500">
                          <Clock className="mr-1 inline h-3 w-3" />
                          {fmtDateTime(b.start_time)} → {fmtTime(b.end_time)}
                        </p>
                      </div>
                      <Countdown start={b.start_time} end={b.end_time} compact />
                      {canConnect && (
                        <button
                          type="button"
                          onClick={() => connectBooking(b.id)}
                          className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700"
                        >
                          <Terminal className="h-3 w-3" />
                          SSH
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}

      {session && (
        <SessionLaunchModal
          session={session.data}
          bookingId={session.bookingId}
          onSessionReplaced={(next) =>
            setSession({ data: next, bookingId: session.bookingId })
          }
          onClose={() => setSession(null)}
        />
      )}
    </div>
  );
}

function AccessRow({
  icon,
  title,
  subtitle,
  meta,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: React.ReactNode;
  meta?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-3">
      <div className="shrink-0">{icon}</div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-bold">{title}</p>
        <p className="truncate text-xs text-slate-500">{subtitle}</p>
      </div>
      {meta && <div className="shrink-0">{meta}</div>}
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AuthGate>
      <DashboardInner />
    </AuthGate>
  );
}
