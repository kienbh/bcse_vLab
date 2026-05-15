"use client";

import { Activity, AlertTriangle, Clock, X } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Session = {
  session_id: string;
  booking_id: string;
  device: string;
  user_email: string;
  user_name: string;
  started_at: string;
  ends_at: string;
  fingerprint: string;
};

function SessionsInner() {
  const { user } = useUser();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(`${API}/sessions/active`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        if (alive) {
          setSessions(d);
          setLoading(false);
        }
      });
    const id = setInterval(() => setTick((t) => t + 1), 15_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [tick]);

  const onKick = async (id: string) => {
    if (!confirm("Kick phiên này? SSH key sẽ bị revoke.")) return;
    const r = await fetch(`${API}/sessions/${id}/kick`, {
      method: "POST",
      credentials: "include",
    });
    if (r.ok) setTick((t) => t + 1);
    else alert("Không kick được — xem console.");
  };

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="surface flex items-center gap-3 p-6">
          <AlertTriangle className="h-5 w-5 text-amber-500" />
          <p className="text-sm">Trang này chỉ dành cho lecturer / admin.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <AdminPageHeader
        title="Phiên SSH đang hoạt động"
        subtitle={<>Tự động làm mới mỗi 15 giây. Tổng: <span className="font-semibold">{sessions.length}</span></>}
        actions={
          <button
            type="button"
            onClick={() => setTick((t) => t + 1)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            Refresh
          </button>
        }
      />

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : sessions.length === 0 ? (
        <div className="surface flex flex-col items-center gap-3 p-12 text-center">
          <Activity className="h-10 w-10 text-slate-300" />
          <p className="text-sm text-slate-500">Không có phiên nào đang chạy.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {sessions.map((s) => (
            <li key={s.session_id} className="surface flex items-center gap-4 p-4">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-700 text-white">
                <Activity className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-mono text-xs uppercase text-slate-500">{s.device}</p>
                <p className="text-sm font-semibold">{s.user_name}</p>
                <p className="text-xs text-slate-500">
                  <Clock className="mr-1 inline h-3 w-3" />
                  {new Date(s.started_at).toLocaleTimeString("vi-VN")} →{" "}
                  {new Date(s.ends_at).toLocaleTimeString("vi-VN")} · {s.user_email}
                </p>
                <p className="font-mono text-[10px] text-slate-400">{s.fingerprint}</p>
              </div>
              <button
                type="button"
                onClick={() => onKick(s.session_id)}
                className="inline-flex items-center gap-1 rounded-md bg-rose-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-rose-600"
              >
                <X className="h-4 w-4" />
                Kick
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AdminSessionsPage() {
  return (
    <AuthGate>
      <SessionsInner />
    </AuthGate>
  );
}
