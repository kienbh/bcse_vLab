"use client";

import { Check, Inbox, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type PendingReq = {
  booking_id: string;
  requester_display: string;
  device_name: string;
  start_time: string;
  end_time: string;
  request_reason: string | null;
  created_at: string;
};

function RequestsInner() {
  const { user } = useUser();
  const [list, setList] = useState<PendingReq[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    fetch(`${API}/requests/pending`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        setList(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl surface p-10">Cần lecturer/admin.</div>;
  }

  const decide = async (id: string, action: "approve" | "reject") => {
    setErr(null);
    let note: string | null = null;
    if (action === "reject") {
      note = window.prompt("Lý do từ chối (tùy chọn):") ?? "";
    }
    const r = await fetch(`${API}/requests/${id}/${action}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision_note: note }),
    });
    if (r.ok) {
      refresh();
    } else {
      const e = await r.json().catch(() => ({}));
      setErr(e?.detail?.hint || e?.detail?.code || `HTTP ${r.status}`);
    }
  };

  const fmt = (s: string) =>
    new Date(s).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-5 px-4 py-10 md:px-6">
      <AdminPageHeader title="Duyệt đề xuất" subtitle={`${list.length} yêu cầu đang chờ duyệt`} />

      {err && (
        <div className="surface border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {err}
        </div>
      )}

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : list.length === 0 ? (
        <div className="surface flex flex-col items-center gap-2 p-12 text-center">
          <Inbox className="h-10 w-10 text-slate-300" />
          <p className="text-sm text-slate-500">Không có đề xuất nào chờ duyệt.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {list.map((r) => (
            <li
              key={r.booking_id}
              className="surface flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between"
            >
              <div>
                <p className="font-semibold">
                  {r.requester_display} ·{" "}
                  <span className="text-vju-600 dark:text-vju-300">{r.device_name}</span>
                </p>
                <p className="text-xs text-slate-500">
                  {fmt(r.start_time)} → {fmt(r.end_time)}
                </p>
                {r.request_reason && (
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                    &ldquo;{r.request_reason}&rdquo;
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => decide(r.booking_id, "approve")}
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
                >
                  <Check className="h-4 w-4" /> Duyệt
                </button>
                <button
                  type="button"
                  onClick={() => decide(r.booking_id, "reject")}
                  className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/30"
                >
                  <X className="h-4 w-4" /> Từ chối
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AdminRequestsPage() {
  return (
    <AuthGate>
      <RequestsInner />
    </AuthGate>
  );
}
