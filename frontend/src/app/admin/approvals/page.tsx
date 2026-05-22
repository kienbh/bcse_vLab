"use client";

import { Check, ClipboardCheck, Clock, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Pending = {
  id: string;
  student_name: string;
  student_email: string;
  student_code: string | null;
  device_name: string;
  start_time: string;
  end_time: string;
  granted_via: string;
  notes: string | null;
};

const fmt = (iso: string) =>
  new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });

function ApprovalsInner() {
  const { user } = useUser();
  const [rows, setRows] = useState<Pending[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/bookings/pending`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  const decide = async (id: string, action: "approve" | "reject") => {
    let url = `${API}/bookings/${id}/${action}`;
    if (action === "reject") {
      const note = prompt("Lý do từ chối (tuỳ chọn):") ?? "";
      if (note) url += `?note=${encodeURIComponent(note)}`;
    }
    setBusy(id);
    const r = await fetch(url, { method: "POST", credentials: "include" });
    setBusy(null);
    if (r.ok) load();
    else {
      const e = await r.json().catch(() => ({}));
      alert(`Lỗi: ${e?.detail?.code ?? r.status}`);
    }
  };

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl p-10 surface">Cần quyền lecturer/admin.</div>;
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <ClipboardCheck className="h-7 w-7 text-vju-500" />
            Duyệt đặt lịch
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {rows.length} yêu cầu chờ duyệt. Duyệt thì sinh viên mới connect được.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Làm mới
        </button>
      </header>

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : rows.length === 0 ? (
        <div className="surface flex flex-col items-center gap-3 p-12 text-center">
          <Clock className="h-10 w-10 text-slate-300" />
          <p className="text-sm text-slate-500">Không có yêu cầu nào chờ duyệt.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {rows.map((p) => (
            <li key={p.id} className="surface flex flex-wrap items-center justify-between gap-3 p-5">
              <div>
                <p className="text-base font-semibold">
                  {p.student_name}{" "}
                  <span className="text-xs font-normal text-slate-500">
                    {p.student_code ?? p.student_email}
                  </span>
                </p>
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {p.device_name} · {fmt(p.start_time)} → {fmt(p.end_time)}
                </p>
                <p className="text-xs text-slate-400">
                  qua {p.granted_via === "class" ? "lớp" : "quyền riêng"}
                  {p.notes ? ` · "${p.notes}"` : ""}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy === p.id}
                  onClick={() => decide(p.id, "approve")}
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  <Check className="h-3.5 w-3.5" /> Duyệt
                </button>
                <button
                  type="button"
                  disabled={busy === p.id}
                  onClick={() => decide(p.id, "reject")}
                  className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-800 dark:hover:bg-rose-950"
                >
                  <X className="h-3.5 w-3.5" /> Từ chối
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AdminApprovalsPage() {
  return (
    <AuthGate>
      <ApprovalsInner />
    </AuthGate>
  );
}
