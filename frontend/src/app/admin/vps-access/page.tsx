"use client";

import { Check, Clock, Inbox, Plus, Server, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { apiPost, useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const MAX_DAYS = 30;

type Device = {
  id: string;
  name: string;
  device_type: string;
};

type AccessRequest = {
  id: string;
  student_id: string;
  device_id: string;
  requested_from: string;
  requested_to: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  decision_note: string | null;
  granted_access_id: string | null;
  created_at: string;
  student_email: string | null;
  student_name: string | null;
  device_name: string | null;
};

type Grant = {
  id: string;
  user_id: string;
  device_id: string;
  valid_from: string;
  valid_to: string;
  reason: string;
  granted_at: string;
  revoked_at: string | null;
  student_email: string | null;
  student_name: string | null;
  device_name: string | null;
};

function fmt(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}
function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function diffDays(fromIso: string, toIso: string) {
  const ms = new Date(toIso).getTime() - new Date(fromIso).getTime();
  return Math.max(1, Math.round(ms / 86_400_000));
}

function Inner() {
  const { user } = useUser();
  const [tab, setTab] = useState<"pending" | "grants" | "history">("pending");
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [vpsList, setVpsList] = useState<Device[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showGrantForm, setShowGrantForm] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [rPending, rGrants, rDevices] = await Promise.all([
        fetch(`${API}/vps-access/requests?status=pending`, { credentials: "include" }),
        fetch(`${API}/vps-access/grants?active_only=true`, { credentials: "include" }),
        fetch(`${API}/devices`, { credentials: "include" }),
      ]);
      if (rPending.ok) setRequests(await rPending.json());
      if (rGrants.ok) setGrants(await rGrants.json());
      if (rDevices.ok) {
        const all: Device[] = await rDevices.json();
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

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl surface p-10">Cần lecturer/admin.</div>;
  }

  const decide = async (id: string, action: "approve" | "reject") => {
    setErr(null);
    let note: string | null = null;
    if (action === "reject") {
      note = window.prompt("Lý do từ chối (tuỳ chọn):") ?? "";
    }
    const r = await apiPost(`/vps-access/requests/${id}/${action}`, {
      decision_note: note || null,
    });
    if (r.ok) {
      refresh();
    } else {
      const e = await r.json().catch(() => ({}));
      setErr(e?.detail?.message || e?.detail?.code || `HTTP ${r.status}`);
    }
  };

  const revoke = async (grantId: string) => {
    if (!window.confirm("Thu hồi quyền truy cập VPS này?")) return;
    const r = await fetch(`${API}/vps-access/grants/${grantId}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (r.ok) {
      refresh();
    } else {
      setErr(`HTTP ${r.status}`);
    }
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5 px-4 py-10 md:px-6">
      <AdminPageHeader
        title="Quyền VPS"
        subtitle={`Cấp / thu hồi truy cập VPS (tối đa ${MAX_DAYS} ngày liên tiếp).`}
      />

      {err && (
        <div className="surface border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {err}
        </div>
      )}

      <div className="flex gap-2 border-b border-slate-200 dark:border-slate-800">
        {(
          [
            ["pending", `Yêu cầu chờ duyệt (${requests.length})`],
            ["grants", `Đang có quyền (${grants.length})`],
            ["history", "Cấp quyền trực tiếp"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => {
              setTab(k);
              if (k === "history") setShowGrantForm(true);
            }}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold transition ${
              tab === k
                ? "border-vju-500 text-vju-600 dark:text-vju-300"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <div className="surface h-32 animate-pulse" />}

      {!loading && tab === "pending" && (
        <PendingList requests={requests} onDecide={decide} />
      )}

      {!loading && tab === "grants" && (
        <GrantList grants={grants} onRevoke={revoke} />
      )}

      {!loading && tab === "history" && (
        <DirectGrantForm
          vpsList={vpsList}
          show={showGrantForm}
          onClose={() => setShowGrantForm(false)}
          onCreated={refresh}
        />
      )}
    </div>
  );
}

function PendingList({
  requests,
  onDecide,
}: {
  requests: AccessRequest[];
  onDecide: (id: string, action: "approve" | "reject") => void;
}) {
  if (requests.length === 0) {
    return (
      <div className="surface flex flex-col items-center gap-2 p-12 text-center">
        <Inbox className="h-10 w-10 text-slate-300" />
        <p className="text-sm text-slate-500">Không có yêu cầu nào chờ duyệt.</p>
      </div>
    );
  }
  return (
    <ul className="space-y-3">
      {requests.map((r) => (
        <li
          key={r.id}
          className="surface flex flex-col gap-3 p-4 md:flex-row md:items-start md:justify-between"
        >
          <div className="flex-1 space-y-1">
            <p className="font-semibold">
              {r.student_name || r.student_email || r.student_id} ·{" "}
              <span className="text-indigo-600 dark:text-indigo-300">{r.device_name}</span>
            </p>
            <p className="text-xs text-slate-500">
              <Clock className="mr-1 inline h-3 w-3" />
              {fmtDate(r.requested_from)} → {fmtDate(r.requested_to)} ({diffDays(r.requested_from, r.requested_to)} ngày) ·
              gửi {fmt(r.created_at)}
            </p>
            <p className="text-sm text-slate-600 dark:text-slate-300">&ldquo;{r.reason}&rdquo;</p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => onDecide(r.id, "approve")}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              <Check className="h-4 w-4" /> Duyệt
            </button>
            <button
              type="button"
              onClick={() => onDecide(r.id, "reject")}
              className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/30"
            >
              <X className="h-4 w-4" /> Từ chối
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function GrantList({
  grants,
  onRevoke,
}: {
  grants: Grant[];
  onRevoke: (id: string) => void;
}) {
  if (grants.length === 0) {
    return (
      <div className="surface flex flex-col items-center gap-2 p-12 text-center">
        <Inbox className="h-10 w-10 text-slate-300" />
        <p className="text-sm text-slate-500">Chưa có ai đang có quyền VPS active.</p>
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {grants.map((g) => {
        const days = diffDays(g.valid_from, g.valid_to);
        const now = Date.now();
        const ends = new Date(g.valid_to).getTime();
        const daysLeft = Math.max(0, Math.ceil((ends - now) / 86_400_000));
        return (
          <li
            key={g.id}
            className="surface flex flex-col gap-2 p-4 md:flex-row md:items-center md:justify-between"
          >
            <div>
              <p className="font-semibold">
                {g.student_name || g.student_email || g.user_id} ·{" "}
                <Server className="ml-1 inline h-3 w-3 text-indigo-500" />{" "}
                <span className="text-indigo-600 dark:text-indigo-300">{g.device_name}</span>
              </p>
              <p className="text-xs text-slate-500">
                {fmtDate(g.valid_from)} → {fmtDate(g.valid_to)} ({days} ngày, còn {daysLeft} ngày) · cấp{" "}
                {fmt(g.granted_at)}
              </p>
              <p className="text-sm text-slate-500">{g.reason}</p>
            </div>
            <button
              type="button"
              onClick={() => onRevoke(g.id)}
              className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/30"
            >
              <Trash2 className="h-3.5 w-3.5" /> Thu hồi
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function DirectGrantForm({
  vpsList,
  show,
  onClose,
  onCreated,
}: {
  vpsList: Device[];
  show: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const today = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, []);
  const [email, setEmail] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const days = useMemo(() => {
    if (!from || !to) return 0;
    return Math.max(1, Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86_400_000) + 1);
  }, [from, to]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    if (days > MAX_DAYS) {
      setMsg(`× Khoảng truy cập tối đa ${MAX_DAYS} ngày.`);
      return;
    }
    setBusy(true);
    const payload = {
      user_email: email.trim(),
      device_id: deviceId,
      valid_from: new Date(`${from}T00:00:00`).toISOString(),
      valid_to: new Date(`${to}T23:59:59`).toISOString(),
      reason: reason.trim(),
    };
    const r = await apiPost("/vps-access/grants", payload);
    setBusy(false);
    if (r.ok) {
      setMsg("✓ Đã cấp quyền VPS.");
      setEmail("");
      setReason("");
      onCreated();
    } else {
      const e2 = await r.json().catch(() => ({}));
      setMsg(`× ${e2?.detail?.message || e2?.detail?.code || `HTTP ${r.status}`}`);
    }
  };

  if (!show) {
    return (
      <div className="surface flex items-center justify-between p-4">
        <p className="text-sm text-slate-500">Cấp quyền trực tiếp cho sinh viên (không cần SV gửi yêu cầu).</p>
        <button
          type="button"
          onClick={() => onClose()}
          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" /> Cấp mới
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="surface flex flex-col gap-3 p-5">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold">Email sinh viên</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="sv01@st.vju.ac.vn"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
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
                {v.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold">Từ ngày</span>
          <input
            type="date"
            required
            value={from}
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
          placeholder="VD: Khoá luận tốt nghiệp — triển khai web back-end"
          className="min-h-[60px] rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={busy || days > MAX_DAYS}
          className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {busy ? "Đang lưu..." : "Cấp quyền"}
        </button>
        {msg && (
          <p
            className={`text-xs ${msg.startsWith("✓") ? "text-emerald-600" : "text-rose-600"}`}
          >
            {msg}
          </p>
        )}
      </div>
    </form>
  );
}

export default function AdminVpsAccessPage() {
  return (
    <AuthGate>
      <Inner />
    </AuthGate>
  );
}
