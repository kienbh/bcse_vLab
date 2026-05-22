"use client";

import { KeyRound, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Cls = { id: string; code: string; name: string };
type Device = { id: string; name: string; model: string; device_type: string };
type Assignment = {
  id: string;
  class_id: string;
  device_id: string;
  valid_from: string;
  valid_to: string;
  per_student_weekly_hours: number;
  per_student_max_concurrent: number;
  per_student_max_advance_days: number;
  revoked_at: string | null;
};
type SpecialAccess = {
  id: string;
  user_email: string;
  user_name: string;
  device_id: string;
  device_name: string;
  valid_from: string;
  valid_to: string;
  weekly_hours_limit: number | null;
  reason: string;
  granted_at: string;
  revoked_at: string | null;
};

const j = (r: Response) => (r.ok ? r.json() : Promise.reject(r));
const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
async function errText(r: Response): Promise<string> {
  const e = await r.json().catch(() => ({}));
  return e?.detail?.code ?? e?.detail ?? `HTTP ${r.status}`;
}

// ----------------------------------------------------------------- class tab
function ClassAccessTab({ classes, devices }: { classes: Cls[]; devices: Device[] }) {
  const deviceName = useMemo(
    () => Object.fromEntries(devices.map((d) => [d.id, d.name])),
    [devices],
  );
  const [classId, setClassId] = useState("");
  const [rows, setRows] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);

  const blankForm = {
    device_id: "",
    valid_from: "",
    valid_to: "",
    per_student_weekly_hours: 20,
    per_student_max_concurrent: 1,
    per_student_max_advance_days: 14,
  };
  const [form, setForm] = useState(blankForm);

  const load = useCallback((cid: string) => {
    if (!cid) {
      setRows([]);
      return;
    }
    setLoading(true);
    fetch(`${API}/classes/${cid}/devices`, { credentials: "include" })
      .then(j)
      .then((d) => setRows(d))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => load(classId), [classId, load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await fetch(`${API}/classes/${classId}/devices`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: form.device_id,
        valid_from: new Date(form.valid_from).toISOString(),
        valid_to: new Date(form.valid_to).toISOString(),
        allowed_time_windows: [],
        per_student_weekly_hours: Number(form.per_student_weekly_hours),
        per_student_max_concurrent: Number(form.per_student_max_concurrent),
        per_student_max_advance_days: Number(form.per_student_max_advance_days),
      }),
    });
    if (r.ok) {
      setShowAdd(false);
      setForm(blankForm);
      load(classId);
    } else alert(`Gán thất bại: ${await errText(r)}`);
  };

  const saveEdit = async (a: Assignment) => {
    const r = await fetch(`${API}/classes/${classId}/devices/${a.id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        valid_to: new Date(a.valid_to).toISOString(),
        per_student_weekly_hours: Number(a.per_student_weekly_hours),
        per_student_max_concurrent: Number(a.per_student_max_concurrent),
        per_student_max_advance_days: Number(a.per_student_max_advance_days),
      }),
    });
    if (r.ok) {
      setEditId(null);
      load(classId);
    } else alert(`Sửa thất bại: ${await errText(r)}`);
  };

  const revoke = async (id: string) => {
    if (!confirm("Thu hồi quyền của lớp với thiết bị này?")) return;
    const r = await fetch(`${API}/classes/${classId}/devices/${id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (r.ok) load(classId);
    else alert(`Thu hồi thất bại: ${await errText(r)}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Field label="Chọn lớp">
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            className="mt-1 w-72 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">— chọn lớp —</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} · {c.name}
              </option>
            ))}
          </select>
        </Field>
        {classId && (
          <button
            type="button"
            onClick={() => setShowAdd((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white"
          >
            <Plus className="h-4 w-4" />
            {showAdd ? "Đóng" : "Gán thiết bị"}
          </button>
        )}
      </div>

      {showAdd && classId && (
        <form onSubmit={create} className="surface grid gap-3 p-5 md:grid-cols-2">
          <Field label="Thiết bị">
            <select
              required
              value={form.device_id}
              onChange={(e) => setForm({ ...form, device_id: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">— chọn thiết bị —</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.device_type})
                </option>
              ))}
            </select>
          </Field>
          <div />
          <TextInput label="Hiệu lực từ" type="datetime-local" value={form.valid_from} onChange={(v) => setForm({ ...form, valid_from: v })} />
          <TextInput label="Hiệu lực đến" type="datetime-local" value={form.valid_to} onChange={(v) => setForm({ ...form, valid_to: v })} />
          <TextInput label="Giờ/tuần mỗi SV" type="number" value={String(form.per_student_weekly_hours)} onChange={(v) => setForm({ ...form, per_student_weekly_hours: Number(v) })} />
          <TextInput label="Số phiên đồng thời" type="number" value={String(form.per_student_max_concurrent)} onChange={(v) => setForm({ ...form, per_student_max_concurrent: Number(v) })} />
          <TextInput label="Đặt trước tối đa (ngày)" type="number" value={String(form.per_student_max_advance_days)} onChange={(v) => setForm({ ...form, per_student_max_advance_days: Number(v) })} />
          <div className="flex items-end">
            <button type="submit" className="w-full rounded-md bg-vju-500 px-4 py-2 text-sm font-semibold text-white">
              Gán
            </button>
          </div>
        </form>
      )}

      {!classId ? (
        <div className="surface p-10 text-center text-sm text-slate-500">
          Chọn một lớp để xem &amp; quản lý thiết bị lớp đó được phép dùng.
        </div>
      ) : loading ? (
        <div className="surface h-24 animate-pulse" />
      ) : rows.length === 0 ? (
        <div className="surface p-10 text-center text-sm text-slate-500">
          Lớp này chưa được gán thiết bị nào.
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((a) => (
            <li key={a.id} className="surface p-4">
              {editId === a.id ? (
                <div className="grid gap-3 md:grid-cols-4">
                  <TextInput label="Hiệu lực đến" type="datetime-local" value={a.valid_to.slice(0, 16)} onChange={(v) => setRows((rs) => rs.map((x) => (x.id === a.id ? { ...x, valid_to: v } : x)))} />
                  <TextInput label="Giờ/tuần" type="number" value={String(a.per_student_weekly_hours)} onChange={(v) => setRows((rs) => rs.map((x) => (x.id === a.id ? { ...x, per_student_weekly_hours: Number(v) } : x)))} />
                  <TextInput label="Đồng thời" type="number" value={String(a.per_student_max_concurrent)} onChange={(v) => setRows((rs) => rs.map((x) => (x.id === a.id ? { ...x, per_student_max_concurrent: Number(v) } : x)))} />
                  <TextInput label="Đặt trước (ngày)" type="number" value={String(a.per_student_max_advance_days)} onChange={(v) => setRows((rs) => rs.map((x) => (x.id === a.id ? { ...x, per_student_max_advance_days: Number(v) } : x)))} />
                  <div className="flex gap-2 md:col-span-4">
                    <button type="button" onClick={() => saveEdit(a)} className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white">
                      Lưu
                    </button>
                    <button type="button" onClick={() => { setEditId(null); load(classId); }} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold dark:border-slate-700">
                      Huỷ
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{deviceName[a.device_id] ?? a.device_id}</p>
                    <p className="text-xs text-slate-500">
                      {fmtDate(a.valid_from)} → {fmtDate(a.valid_to)} · {a.per_student_weekly_hours}h/tuần ·{" "}
                      {a.per_student_max_concurrent} phiên · đặt trước {a.per_student_max_advance_days}d
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setEditId(a.id)} className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                      <Pencil className="h-3 w-3" /> Sửa
                    </button>
                    <button type="button" onClick={() => revoke(a.id)} className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-800 dark:hover:bg-rose-950">
                      <Trash2 className="h-3 w-3" /> Thu hồi
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-500">
        ⓘ Gán thiết bị cho lớp = mọi sinh viên đã enroll lớp đó được phép đặt lịch thiết bị, trong
        hạn mức trên. Truy cập theo khung giờ 24/7 (chưa giới hạn khung giờ).
      </p>
    </div>
  );
}

// --------------------------------------------------------------- special tab
function SpecialAccessTab({ devices }: { devices: Device[] }) {
  const [rows, setRows] = useState<SpecialAccess[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const blankForm = {
    user_email: "",
    device_id: "",
    valid_from: "",
    valid_to: "",
    weekly_hours_limit: "",
    reason: "",
  };
  const [form, setForm] = useState(blankForm);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/teacher/special-access`, { credentials: "include" })
      .then(j)
      .then((d) => setRows(d))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await fetch(`${API}/teacher/special-access`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_email: form.user_email.trim().toLowerCase(),
        device_id: form.device_id,
        valid_from: new Date(form.valid_from).toISOString(),
        valid_to: new Date(form.valid_to).toISOString(),
        allowed_time_windows: [],
        weekly_hours_limit: form.weekly_hours_limit ? Number(form.weekly_hours_limit) : null,
        reason: form.reason.trim(),
      }),
    });
    if (r.ok) {
      setShowAdd(false);
      setForm(blankForm);
      load();
    } else alert(`Cấp quyền thất bại: ${await errText(r)}`);
  };

  const revoke = async (id: string) => {
    if (!confirm("Thu hồi quyền riêng này?")) return;
    const r = await fetch(`${API}/teacher/special-access/${id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (r.ok) load();
    else alert(`Thu hồi thất bại: ${await errText(r)}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setShowAdd((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white"
        >
          <Plus className="h-4 w-4" />
          {showAdd ? "Đóng" : "Cấp quyền riêng"}
        </button>
      </div>

      {showAdd && (
        <form onSubmit={create} className="surface grid gap-3 p-5 md:grid-cols-2">
          <TextInput label="Email sinh viên" value={form.user_email} onChange={(v) => setForm({ ...form, user_email: v })} placeholder="sv01@st.vju.ac.vn" />
          <Field label="Thiết bị">
            <select
              required
              value={form.device_id}
              onChange={(e) => setForm({ ...form, device_id: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">— chọn thiết bị —</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.device_type})
                </option>
              ))}
            </select>
          </Field>
          <TextInput label="Hiệu lực từ" type="datetime-local" value={form.valid_from} onChange={(v) => setForm({ ...form, valid_from: v })} />
          <TextInput label="Hiệu lực đến" type="datetime-local" value={form.valid_to} onChange={(v) => setForm({ ...form, valid_to: v })} />
          <TextInput label="Giới hạn giờ/tuần (trống = quota chung)" type="number" required={false} value={form.weekly_hours_limit} onChange={(v) => setForm({ ...form, weekly_hours_limit: v })} />
          <TextInput label="Lý do (≥10 ký tự)" value={form.reason} onChange={(v) => setForm({ ...form, reason: v })} placeholder="Khoá luận tốt nghiệp..." />
          <button type="submit" className="md:col-span-2 rounded-md bg-vju-500 px-4 py-2 text-sm font-semibold text-white">
            Cấp quyền
          </button>
        </form>
      )}

      {loading ? (
        <div className="surface h-24 animate-pulse" />
      ) : rows.length === 0 ? (
        <div className="surface p-10 text-center text-sm text-slate-500">
          Chưa có quyền riêng nào được cấp.
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((s) => (
            <li
              key={s.id}
              className={`surface p-4 ${s.revoked_at ? "opacity-50" : ""}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-semibold">
                    {s.user_name}{" "}
                    <span className="font-normal text-slate-500">({s.user_email})</span>
                    {" → "}
                    {s.device_name}
                  </p>
                  <p className="text-xs text-slate-500">
                    {fmtDate(s.valid_from)} → {fmtDate(s.valid_to)} ·{" "}
                    {s.weekly_hours_limit ? `${s.weekly_hours_limit}h/tuần` : "quota chung"} ·{" "}
                    {s.reason}
                    {s.revoked_at && " · ĐÃ THU HỒI"}
                  </p>
                </div>
                {!s.revoked_at && (
                  <button
                    type="button"
                    onClick={() => revoke(s.id)}
                    className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-800 dark:hover:bg-rose-950"
                  >
                    <Trash2 className="h-3 w-3" /> Thu hồi
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-500">
        ⓘ Quyền riêng = cấp cho một sinh viên cụ thể quyền dùng một thiết bị, không phụ thuộc lớp
        (vd làm khoá luận). Dùng khi sinh viên không enroll lớp có thiết bị đó.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------- shell
function AccessInner() {
  const { user } = useUser();
  const [tab, setTab] = useState<"class" | "special">("class");
  const [classes, setClasses] = useState<Cls[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);

  useEffect(() => {
    fetch(`${API}/classes`, { credentials: "include" }).then(j).then(setClasses).catch(() => {});
    fetch(`${API}/devices`, { credentials: "include" }).then(j).then(setDevices).catch(() => {});
  }, []);

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl p-10 surface">Cần quyền lecturer/admin.</div>;
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Quản lý quyền truy cập</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Gán thiết bị cho lớp, hoặc cấp quyền riêng cho từng sinh viên.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        <TabButton active={tab === "class"} onClick={() => setTab("class")} icon={<ShieldCheck className="h-4 w-4" />}>
          Quyền theo lớp
        </TabButton>
        <TabButton active={tab === "special"} onClick={() => setTab("special")} icon={<KeyRound className="h-4 w-4" />}>
          Quyền riêng (per-SV)
        </TabButton>
      </div>

      {tab === "class" ? (
        <ClassAccessTab classes={classes} devices={devices} />
      ) : (
        <SpecialAccessTab devices={devices} />
      )}
    </div>
  );
}

// --------------------------------------------------------------- ui helpers
function TabButton({
  active, onClick, icon, children,
}: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition ${
        active
          ? "border-vju-500 text-vju-600 dark:text-vju-400"
          : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
      {label}
      {children}
    </label>
  );
}

function TextInput({
  label, value, onChange, type = "text", placeholder, required = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <Field label={label}>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </Field>
  );
}

export default function AdminAccessPage() {
  return (
    <AuthGate>
      <AccessInner />
    </AuthGate>
  );
}
