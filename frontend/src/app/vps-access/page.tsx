"use client";

import { CheckCircle2, Clock, Plus, Server, X, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { apiPost, useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const MAX_DAYS = 30;

type Device = {
  id: string;
  name: string;
  device_type: string;
  model: string;
  capabilities: Record<string, unknown>;
};

type AccessRequest = {
  id: string;
  device_id: string;
  requested_from: string;
  requested_to: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  decision_note: string | null;
  granted_access_id: string | null;
  created_at: string;
  device_name: string | null;
};

type Grant = {
  id: string;
  device_id: string;
  valid_from: string;
  valid_to: string;
  reason: string;
  granted_at: string;
  revoked_at: string | null;
  device_name: string | null;
};

function fmt(iso: string) {
  return new Date(iso).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function diffDaysInclusive(fromIso: string, toIso: string) {
  return Math.max(
    1,
    Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 86_400_000) + 1,
  );
}

function StatusBadge({ status }: { status: AccessRequest["status"] }) {
  const cfg = {
    pending: { label: "Đang chờ duyệt", cls: "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200" },
    approved: { label: "Đã duyệt", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200" },
    rejected: { label: "Từ chối", cls: "bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200" },
    cancelled: { label: "Đã huỷ", cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  }[status];
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function Inner() {
  const { user } = useUser();
  const [grants, setGrants] = useState<Grant[]>([]);
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [vpsList, setVpsList] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [rG, rR, rD] = await Promise.all([
        fetch(`${API}/vps-access/grants/mine`, { credentials: "include" }),
        fetch(`${API}/vps-access/requests/mine`, { credentials: "include" }),
        fetch(`${API}/devices`, { credentials: "include" }),
      ]);
      if (rG.ok) setGrants(await rG.json());
      if (rR.ok) setRequests(await rR.json());
      if (rD.ok) {
        const all: Device[] = await rD.json();
        setVpsList(all.filter((d) => d.device_type === "vps"));
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!user) return null;

  const cancel = async (id: string) => {
    if (!window.confirm("Huỷ yêu cầu này?")) return;
    const r = await apiPost(`/vps-access/requests/${id}/cancel`);
    if (r.ok) refresh();
    else setErr(`HTTP ${r.status}`);
  };

  const now = Date.now();
  const activeGrants = grants.filter(
    (g) => !g.revoked_at && new Date(g.valid_from).getTime() <= now && new Date(g.valid_to).getTime() >= now,
  );
  const pastGrants = grants.filter((g) => !activeGrants.includes(g));
  const pendingRequests = requests.filter((r) => r.status === "pending");
  const decidedRequests = requests.filter((r) => r.status !== "pending");

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 text-white shadow-md">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Quyền VPS của tôi</h1>
            <p className="text-sm text-slate-500">
              Yêu cầu quyền dài ngày (tối đa {MAX_DAYS} ngày) tới giảng viên.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" /> Yêu cầu mới
        </button>
      </header>

      {err && (
        <div className="surface border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {err}
        </div>
      )}

      {showForm && (
        <RequestForm
          vpsList={vpsList}
          onClose={() => setShowForm(false)}
          onCreated={() => {
            setShowForm(false);
            refresh();
          }}
        />
      )}

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : (
        <>
          <Section title="Đang có quyền" count={activeGrants.length}>
            {activeGrants.length === 0 ? (
              <Empty msg="Chưa có quyền VPS active. Gửi yêu cầu hoặc liên hệ giảng viên." />
            ) : (
              activeGrants.map((g) => <ActiveGrantCard key={g.id} grant={g} />)
            )}
          </Section>

          {pendingRequests.length > 0 && (
            <Section title="Yêu cầu đang chờ duyệt" count={pendingRequests.length}>
              {pendingRequests.map((r) => (
                <RequestRow key={r.id} req={r} onCancel={() => cancel(r.id)} />
              ))}
            </Section>
          )}

          {pastGrants.length > 0 && (
            <Section title="Lịch sử quyền" count={pastGrants.length}>
              {pastGrants.map((g) => (
                <div
                  key={g.id}
                  className="surface flex items-center justify-between p-3 text-sm opacity-70"
                >
                  <div>
                    <p className="font-semibold">{g.device_name}</p>
                    <p className="text-xs text-slate-500">
                      {fmt(g.valid_from)} → {fmt(g.valid_to)}
                      {g.revoked_at && " · Đã thu hồi"}
                    </p>
                  </div>
                </div>
              ))}
            </Section>
          )}

          {decidedRequests.length > 0 && (
            <Section title="Yêu cầu đã xử lý" count={decidedRequests.length}>
              {decidedRequests.map((r) => (
                <RequestRow key={r.id} req={r} />
              ))}
            </Section>
          )}
        </>
      )}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-baseline gap-2 text-sm font-bold uppercase tracking-wide text-slate-600 dark:text-slate-300">
        {title}
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {count}
        </span>
      </h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function Empty({ msg }: { msg: string }) {
  return (
    <div className="surface p-6 text-center text-sm text-slate-500">{msg}</div>
  );
}

function ActiveGrantCard({ grant }: { grant: Grant }) {
  const daysLeft = Math.max(
    0,
    Math.ceil((new Date(grant.valid_to).getTime() - Date.now()) / 86_400_000),
  );
  return (
    <div className="surface flex items-center justify-between gap-3 p-4">
      <div>
        <p className="font-semibold">
          <Server className="mr-1 inline h-4 w-4 text-indigo-500" />
          {grant.device_name}
        </p>
        <p className="text-xs text-slate-500">
          <Clock className="mr-1 inline h-3 w-3" />
          {fmt(grant.valid_from)} → {fmt(grant.valid_to)} · còn {daysLeft} ngày
        </p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{grant.reason}</p>
      </div>
      <Link
        href="/devices/vps"
        className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
      >
        Kết nối
      </Link>
    </div>
  );
}

function RequestRow({ req, onCancel }: { req: AccessRequest; onCancel?: () => void }) {
  return (
    <div className="surface flex flex-col gap-2 p-3 md:flex-row md:items-start md:justify-between">
      <div className="flex-1">
        <p className="text-sm">
          <span className="font-semibold">{req.device_name}</span>{" "}
          <StatusBadge status={req.status} />
        </p>
        <p className="text-xs text-slate-500">
          {fmt(req.requested_from)} → {fmt(req.requested_to)} (
          {diffDaysInclusive(req.requested_from, req.requested_to)} ngày)
        </p>
        <p className="text-xs text-slate-600 dark:text-slate-400">&ldquo;{req.reason}&rdquo;</p>
        {req.decision_note && (
          <p className="text-xs italic text-slate-500">GV: {req.decision_note}</p>
        )}
      </div>
      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="self-start inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <X className="h-3 w-3" /> Huỷ
        </button>
      )}
    </div>
  );
}

function RequestForm({
  vpsList,
  onClose,
  onCreated,
}: {
  vpsList: Device[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [deviceId, setDeviceId] = useState("");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const days = useMemo(() => {
    if (!from || !to) return 0;
    return Math.max(
      1,
      Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86_400_000) + 1,
    );
  }, [from, to]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    if (days > MAX_DAYS) {
      setMsg(`× Tối đa ${MAX_DAYS} ngày liên tiếp.`);
      return;
    }
    setBusy(true);
    const payload = {
      device_id: deviceId,
      requested_from: new Date(`${from}T00:00:00`).toISOString(),
      requested_to: new Date(`${to}T23:59:59`).toISOString(),
      reason: reason.trim(),
    };
    const r = await apiPost("/vps-access/requests", payload);
    setBusy(false);
    if (r.ok) {
      setMsg("✓ Đã gửi yêu cầu. Chờ giảng viên duyệt.");
      onCreated();
    } else {
      const e2 = await r.json().catch(() => ({}));
      setMsg(`× ${e2?.detail?.message || e2?.detail?.code || `HTTP ${r.status}`}`);
    }
  };

  return (
    <form onSubmit={submit} className="surface flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Yêu cầu quyền VPS</p>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold">VPS</span>
        <select
          required
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">— Chọn VPS —</option>
          {vpsList.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} — {v.model}
            </option>
          ))}
        </select>
      </label>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold">Từ ngày</span>
          <input
            type="date"
            required
            value={from}
            min={today}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold">
            Đến ngày <span className="font-normal text-slate-400">({days} ngày, tối đa {MAX_DAYS})</span>
          </span>
          <input
            type="date"
            required
            value={to}
            min={from}
            onChange={(e) => setTo(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold">Lý do (≥ 10 ký tự)</span>
        <textarea
          required
          minLength={10}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="VD: Khoá luận tốt nghiệp — chạy web back-end, cần SSH dài ngày"
          className="min-h-[80px] rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={busy || days > MAX_DAYS}
          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Đang gửi..." : "Gửi yêu cầu"}
        </button>
        {msg && (
          <p
            className={`text-xs ${msg.startsWith("✓") ? "text-emerald-600" : "text-rose-600"}`}
          >
            {msg.startsWith("✓") ? (
              <CheckCircle2 className="mr-1 inline h-3 w-3" />
            ) : (
              <XCircle className="mr-1 inline h-3 w-3" />
            )}
            {msg}
          </p>
        )}
      </div>
    </form>
  );
}

export default function VpsAccessPage() {
  return (
    <AuthGate>
      <Inner />
    </AuthGate>
  );
}
