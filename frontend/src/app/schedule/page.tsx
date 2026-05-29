"use client";

import {
  CalendarDays,
  CheckCircle2,
  Clock,
  Inbox,
  Loader2,
  Plug,
  Send,
  Users,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { SessionLaunchModal, SessionResult } from "@/components/BookingModal";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type MySlot = {
  id: string;
  device_id: string;
  device_name: string;
  day_of_week: number;
  time_slot: string;
  starts_hhmm: string;
  ends_hhmm: string;
  is_live_now: boolean;
};
type MySchedule = {
  class_id: string | null;
  class_name: string | null;
  group_id: string | null;
  group_name: string | null;
  is_leader: boolean;
  slots: MySlot[];
};
type Booking = {
  id: string;
  device_id: string;
  start_time: string;
  end_time: string;
  status: string;
  request_reason: string | null;
  decision_note: string | null;
};
type DeviceT = { id: string; name: string };

const DAYS = [
  { v: 1, label: "Thứ 2" },
  { v: 2, label: "Thứ 3" },
  { v: 3, label: "Thứ 4" },
  { v: 4, label: "Thứ 5" },
  { v: 5, label: "Thứ 6" },
  { v: 6, label: "Thứ 7" },
  { v: 7, label: "Chủ nhật" },
];
const SLOTS = [
  { v: "morning", label: "Sáng" },
  { v: "afternoon", label: "Chiều" },
  { v: "evening", label: "Tối" },
];

const REQ_STATUS: Record<string, { label: string; cls: string; icon: typeof Clock }> = {
  pending_approval: {
    label: "Chờ duyệt",
    cls: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
    icon: Clock,
  },
  scheduled: {
    label: "Đã duyệt",
    cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    icon: CheckCircle2,
  },
  active: {
    label: "Đang dùng",
    cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    icon: CheckCircle2,
  },
  rejected: {
    label: "Bị từ chối",
    cls: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
    icon: XCircle,
  },
};

function ScheduleInner() {
  const { user } = useUser();
  const [sched, setSched] = useState<MySchedule | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [devices, setDevices] = useState<DeviceT[]>([]);
  const [session, setSession] = useState<{ data: SessionResult; bookingId: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reqForm, setReqForm] = useState({ device_id: "", start: "", end: "", reason: "" });

  const load = useCallback(async () => {
    try {
      const [s, b, d] = await Promise.all([
        fetch(`${API}/my/schedule`, { credentials: "include" }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${API}/bookings`, { credentials: "include" }).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API}/devices`, { credentials: "include" }).then((r) => (r.ok ? r.json() : [])),
      ]);
      setSched(s);
      setBookings(b);
      setDevices(d);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000); // refresh so is_live_now flips on time
    return () => clearInterval(id);
  }, [load]);

  if (!user) return null;

  const connect = async (slot: MySlot) => {
    setErr(null);
    setBusy(slot.id);
    try {
      const r1 = await fetch(`${API}/planned-slots/${slot.id}/start`, {
        method: "POST",
        credentials: "include",
      });
      if (!r1.ok) {
        const e = await r1.json().catch(() => ({}));
        setErr(e?.detail?.hint || e?.detail?.code || `HTTP ${r1.status}`);
        return;
      }
      const booking = await r1.json();
      const r2 = await fetch(`${API}/bookings/${booking.id}/access`, {
        method: "POST",
        credentials: "include",
      });
      if (!r2.ok) {
        const e = await r2.json().catch(() => ({}));
        setErr(`Không lấy được phiên: ${e?.detail?.code ?? r2.status}`);
        return;
      }
      setSession({ data: await r2.json(), bookingId: booking.id });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  const submitRequest = async () => {
    setErr(null);
    setBusy("request");
    try {
      const r = await fetch(`${API}/requests`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: reqForm.device_id,
          start_time: new Date(reqForm.start).toISOString(),
          end_time: new Date(reqForm.end).toISOString(),
          reason: reqForm.reason,
        }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        setErr(e?.detail?.hint || e?.detail?.code || `HTTP ${r.status}`);
        return;
      }
      setReqForm({ device_id: "", start: "", end: "", reason: "" });
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  const deviceName = (id: string) => devices.find((d) => d.id === id)?.name ?? id;
  const fmt = (s: string) =>
    new Date(s).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });

  // Ad-hoc requests = bookings the student submitted with a reason, or any
  // pending/rejected one — shown with their approval status.
  const myRequests = bookings.filter(
    (b) => b.request_reason || b.status === "pending_approval" || b.status === "rejected",
  );

  const cell = (day: number, slot: string) =>
    (sched?.slots ?? []).filter((s) => s.day_of_week === day && s.time_slot === slot);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-10 md:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Lịch nhóm của tôi</h1>
        {sched?.group_name ? (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <Users className="h-4 w-4" />
            <span className="font-semibold">{sched.group_name}</span>
            {sched.class_name && <span>· {sched.class_name}</span>}
            {sched.is_leader ? (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                👑 Nhóm trưởng
              </span>
            ) : (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500 dark:bg-slate-800">
                Thành viên
              </span>
            )}
          </p>
        ) : (
          <p className="mt-1 text-sm text-slate-500">Bạn chưa được xếp nhóm.</p>
        )}
      </div>

      {err && (
        <div className="surface border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {err}
        </div>
      )}

      {loading ? (
        <div className="surface h-40 animate-pulse" />
      ) : !sched?.group_id ? (
        <div className="surface flex flex-col items-center gap-2 p-12 text-center">
          <Users className="h-10 w-10 text-slate-300" />
          <h2 className="text-base font-semibold">Chưa có nhóm</h2>
          <p className="max-w-md text-sm text-slate-500">
            Giảng viên chưa xếp bạn vào nhóm nào. Liên hệ giảng viên để được thêm vào nhóm + cấp lịch
            sử dụng kit.
          </p>
        </div>
      ) : (
        <>
          {/* weekly grid */}
          <section className="surface overflow-x-auto">
            <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
              <CalendarDays className="h-4 w-4 text-vju-500" />
              <h2 className="text-sm font-semibold">Lịch tuần</h2>
              {!sched.is_leader && (
                <span className="text-xs text-slate-400">
                  — chỉ nhóm trưởng bấm Connect được
                </span>
              )}
            </header>
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-900">
                <tr>
                  <th className="p-2 text-left">Thứ</th>
                  {SLOTS.map((s) => (
                    <th key={s.v} className="p-2 text-left">
                      {s.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DAYS.map((d) => (
                  <tr key={d.v} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="p-2 font-semibold">{d.label}</td>
                    {SLOTS.map((s) => {
                      const items = cell(d.v, s.v);
                      return (
                        <td key={s.v} className="p-2 align-top">
                          {items.length === 0 ? (
                            <span className="text-xs text-slate-300 dark:text-slate-600">—</span>
                          ) : (
                            <div className="flex flex-col gap-1.5">
                              {items.map((slot) => (
                                <div
                                  key={slot.id}
                                  className={`rounded-md border p-2 text-xs ${
                                    slot.is_live_now
                                      ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                                      : "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900"
                                  }`}
                                >
                                  <p className="font-semibold">{slot.device_name}</p>
                                  <p className="text-slate-500">
                                    {slot.starts_hhmm}–{slot.ends_hhmm}
                                  </p>
                                  {slot.is_live_now && (
                                    <button
                                      type="button"
                                      disabled={!sched.is_leader || busy === slot.id}
                                      onClick={() => connect(slot)}
                                      className="mt-1.5 inline-flex w-full items-center justify-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                                      title={
                                        sched.is_leader
                                          ? "Kết nối kit"
                                          : "Chỉ nhóm trưởng được kết nối"
                                      }
                                    >
                                      {busy === slot.id ? (
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                      ) : (
                                        <Plug className="h-3 w-3" />
                                      )}
                                      Connect
                                    </button>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* ad-hoc request — leader only */}
          {sched.is_leader && (
            <section className="surface p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Send className="h-4 w-4 text-vju-500" />
                Xin dùng thêm ngoài lịch
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Nhóm cần dùng kit ngoài lịch tuần → gửi đề xuất, giảng viên duyệt.
              </p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
                  Kit
                  <select
                    value={reqForm.device_id}
                    onChange={(e) => setReqForm({ ...reqForm, device_id: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-900"
                  >
                    <option value="">— chọn kit —</option>
                    {devices.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
                    Bắt đầu
                    <input
                      type="datetime-local"
                      value={reqForm.start}
                      onChange={(e) => setReqForm({ ...reqForm, start: e.target.value })}
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-900"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
                    Kết thúc
                    <input
                      type="datetime-local"
                      value={reqForm.end}
                      onChange={(e) => setReqForm({ ...reqForm, end: e.target.value })}
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-900"
                    />
                  </label>
                </div>
                <label className="block text-xs font-semibold text-slate-600 md:col-span-2 dark:text-slate-400">
                  Lý do
                  <textarea
                    value={reqForm.reason}
                    onChange={(e) => setReqForm({ ...reqForm, reason: e.target.value })}
                    rows={2}
                    placeholder="VD: nhóm cần chạy thêm thí nghiệm cho báo cáo cuối kỳ"
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
              </div>
              <button
                type="button"
                disabled={
                  busy === "request" ||
                  !reqForm.device_id ||
                  !reqForm.start ||
                  !reqForm.end ||
                  reqForm.reason.trim().length < 10
                }
                onClick={submitRequest}
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white hover:bg-vju-600 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {busy === "request" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Gửi đề xuất
              </button>
            </section>
          )}

          {/* my requests + their status */}
          <section className="surface">
            <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
              <Inbox className="h-4 w-4 text-vju-500" />
              <h2 className="text-sm font-semibold">Đề xuất của tôi</h2>
            </header>
            {myRequests.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">Chưa có đề xuất nào.</p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {myRequests.map((b) => {
                  const st = REQ_STATUS[b.status] ?? REQ_STATUS.pending_approval;
                  const Icon = st.icon;
                  return (
                    <li key={b.id} className="flex flex-col gap-1 px-5 py-3 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold">{deviceName(b.device_id)}</span>
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${st.cls}`}
                        >
                          <Icon className="h-3 w-3" />
                          {st.label}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500">
                        {fmt(b.start_time)} → {fmt(b.end_time)}
                      </p>
                      {b.request_reason && (
                        <p className="text-xs text-slate-600 dark:text-slate-300">
                          &ldquo;{b.request_reason}&rdquo;
                        </p>
                      )}
                      {b.status === "rejected" && b.decision_note && (
                        <p className="text-xs text-rose-600 dark:text-rose-400">
                          Lý do từ chối: {b.decision_note}
                        </p>
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
          onSessionReplaced={(next) => setSession({ data: next, bookingId: session.bookingId })}
          onClose={() => setSession(null)}
        />
      )}
    </div>
  );
}

export default function SchedulePage() {
  return (
    <AuthGate>
      <ScheduleInner />
    </AuthGate>
  );
}
