"use client";

import { CalendarClock, KeyRound, Plus, ShieldCheck, Trash2, Users, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Cls = { id: string; code: string; name: string };
type Device = { id: string; name: string; device_type: string };
type Student = { id: string; email: string; full_name: string; student_code: string | null };
type TimeWindow = { day_of_week: number; start: string; end: string };
type Assignment = {
  id: string;
  device_id: string;
  valid_from: string;
  valid_to: string;
  allowed_time_windows: TimeWindow[];
  per_student_weekly_hours: number;
  per_student_max_concurrent: number;
  per_student_max_advance_days: number;
};
type Grant = {
  id: string;
  user_email: string;
  user_name: string;
  device_name: string;
  valid_from: string;
  valid_to: string;
  allowed_time_windows: TimeWindow[];
  weekly_hours_limit: number | null;
  reason: string;
  revoked_at: string | null;
};

const DAYS = ["", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];
const j = (r: Response) => (r.ok ? r.json() : Promise.reject(r));
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("vi-VN");
const dayToIso = (d: string) => new Date(`${d}T00:00:00`).toISOString();
const dayEndToIso = (d: string) => new Date(`${d}T23:59:59`).toISOString();
async function errText(r: Response) {
  const e = await r.json().catch(() => ({}));
  return e?.detail?.code ?? e?.detail ?? `HTTP ${r.status}`;
}
const fmtWindows = (ws: TimeWindow[]) =>
  ws.length === 0
    ? "cả tuần (24/7)"
    : ws.map((w) => `${DAYS[w.day_of_week]} ${w.start}–${w.end}`).join(", ");

// ------------------------------------------------ weekly time-window editor
function WeeklyWindowEditor({
  windows, onChange,
}: { windows: TimeWindow[]; onChange: (w: TimeWindow[]) => void }) {
  const add = () => onChange([...windows, { day_of_week: 1, start: "08:00", end: "11:00" }]);
  const upd = (i: number, patch: Partial<TimeWindow>) =>
    onChange(windows.map((w, k) => (k === i ? { ...w, ...patch } : w)));
  const del = (i: number) => onChange(windows.filter((_, k) => k !== i));

  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-400">
        <CalendarClock className="h-3.5 w-3.5" />
        Khung giờ tuần (để trống = được dùng cả tuần)
      </div>
      <div className="space-y-2">
        {windows.map((w, i) => (
          <div key={i} className="flex items-center gap-2">
            <select
              value={w.day_of_week}
              onChange={(e) => upd(i, { day_of_week: Number(e.target.value) })}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                <option key={d} value={d}>{DAYS[d]}</option>
              ))}
            </select>
            <input
              type="time"
              value={w.start}
              onChange={(e) => upd(i, { start: e.target.value })}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
            <span className="text-slate-400">→</span>
            <input
              type="time"
              value={w.end}
              onChange={(e) => upd(i, { end: e.target.value })}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
            <button type="button" onClick={() => del(i)} className="text-rose-500 hover:text-rose-700">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={add}
        className="mt-2 inline-flex items-center gap-1 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
      >
        <Plus className="h-3 w-3" /> Thêm khung giờ
      </button>
    </div>
  );
}

// ------------------------------------------------------ student-grant tab
function StudentGrantTab({ classes, devices }: { classes: Cls[]; devices: Device[] }) {
  const [classId, setClassId] = useState("");
  const [students, setStudents] = useState<Student[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [grants, setGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [deviceId, setDeviceId] = useState("");
  const [windows, setWindows] = useState<TimeWindow[]>([]);
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [weeklyHours, setWeeklyHours] = useState("");
  const [reason, setReason] = useState("");

  const loadStudents = useCallback((cid: string) => {
    const url = cid ? `${API}/teacher/students?class_id=${cid}` : `${API}/teacher/students`;
    fetch(url, { credentials: "include" }).then(j).then(setStudents).catch(() => setStudents([]));
    setPicked(new Set());
  }, []);
  const loadGrants = useCallback(() => {
    setLoading(true);
    fetch(`${API}/teacher/special-access`, { credentials: "include" })
      .then(j)
      .then(setGrants)
      .catch(() => setGrants([]))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => loadStudents(classId), [classId, loadStudents]);
  useEffect(loadGrants, [loadGrants]);

  const toggle = (id: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const allChecked = students.length > 0 && picked.size === students.length;
  const toggleAll = () =>
    setPicked(allChecked ? new Set() : new Set(students.map((s) => s.id)));

  const grant = async () => {
    if (picked.size === 0) return alert("Chưa chọn sinh viên nào.");
    if (!deviceId || !validFrom || !validTo) return alert("Chọn thiết bị + thời hạn.");
    if (reason.trim().length < 10) return alert("Lý do cần ≥ 10 ký tự.");
    setBusy(true);
    const emails = students.filter((s) => picked.has(s.id)).map((s) => s.email);
    let ok = 0;
    const fails: string[] = [];
    for (const email of emails) {
      const r = await fetch(`${API}/teacher/special-access`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_email: email,
          device_id: deviceId,
          valid_from: dayToIso(validFrom),
          valid_to: dayEndToIso(validTo),
          allowed_time_windows: windows,
          weekly_hours_limit: weeklyHours ? Number(weeklyHours) : null,
          reason: reason.trim(),
        }),
      });
      if (r.ok) ok += 1;
      else fails.push(`${email}: ${await errText(r)}`);
    }
    setBusy(false);
    alert(`Cấp quyền: ${ok} thành công${fails.length ? `, ${fails.length} lỗi:\n${fails.join("\n")}` : ""}`);
    setPicked(new Set());
    loadGrants();
  };

  const revoke = async (id: string) => {
    if (!confirm("Thu hồi quyền này?")) return;
    const r = await fetch(`${API}/teacher/special-access/${id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (r.ok) loadGrants();
    else alert(`Thu hồi lỗi: ${await errText(r)}`);
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 lg:grid-cols-2">
        {/* left: pick students */}
        <div className="surface flex flex-col gap-3 p-5">
          <div className="flex items-center gap-2 text-sm font-bold">
            <Users className="h-4 w-4 text-vju-500" /> 1. Chọn sinh viên
          </div>
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Tất cả sinh viên</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>Lớp: {c.code} · {c.name}</option>
            ))}
          </select>
          {students.length > 0 && (
            <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
              <input type="checkbox" checked={allChecked} onChange={toggleAll} />
              Chọn tất cả ({students.length})
            </label>
          )}
          <div className="max-h-72 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700">
            {students.length === 0 ? (
              <p className="p-4 text-center text-xs text-slate-500">Không có sinh viên.</p>
            ) : (
              students.map((s) => (
                <label
                  key={s.id}
                  className="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-3 py-2 text-sm last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                >
                  <input type="checkbox" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
                  <span className="flex-1">
                    {s.full_name}{" "}
                    <span className="text-xs text-slate-500">
                      {s.student_code ?? s.email}
                    </span>
                  </span>
                </label>
              ))
            )}
          </div>
          <p className="text-xs font-semibold text-vju-600 dark:text-vju-400">
            Đã chọn: {picked.size} sinh viên
          </p>
        </div>

        {/* right: grant config */}
        <div className="surface flex flex-col gap-3 p-5">
          <div className="flex items-center gap-2 text-sm font-bold">
            <ShieldCheck className="h-4 w-4 text-vju-500" /> 2. Cấp thiết bị + khung giờ
          </div>
          <Field label="Thiết bị">
            <select
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">— chọn thiết bị —</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>{d.name} ({d.device_type})</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <TextInput label="Hiệu lực từ" type="date" value={validFrom} onChange={setValidFrom} />
            <TextInput label="Hiệu lực đến" type="date" value={validTo} onChange={setValidTo} />
          </div>
          <WeeklyWindowEditor windows={windows} onChange={setWindows} />
          <div className="grid grid-cols-2 gap-3">
            <TextInput label="Giới hạn giờ/tuần (trống = mặc định)" type="number" required={false} value={weeklyHours} onChange={setWeeklyHours} />
            <TextInput label="Lý do (≥10 ký tự)" value={reason} onChange={setReason} placeholder="Lịch thực hành học kỳ..." />
          </div>
          <button
            type="button"
            onClick={grant}
            disabled={busy}
            className="mt-1 rounded-md bg-vju-500 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Đang cấp..." : `Cấp quyền cho ${picked.size} sinh viên`}
          </button>
        </div>
      </div>

      {/* existing grants */}
      <div>
        <h3 className="mb-2 text-sm font-bold">Quyền đã cấp</h3>
        {loading ? (
          <div className="surface h-20 animate-pulse" />
        ) : grants.length === 0 ? (
          <div className="surface p-8 text-center text-sm text-slate-500">Chưa cấp quyền nào.</div>
        ) : (
          <ul className="space-y-2">
            {grants.map((g) => (
              <li key={g.id} className={`surface p-3 ${g.revoked_at ? "opacity-50" : ""}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">
                      {g.user_name} <span className="font-normal text-slate-500">→ {g.device_name}</span>
                    </p>
                    <p className="text-xs text-slate-500">
                      {fmtDate(g.valid_from)}–{fmtDate(g.valid_to)} · {fmtWindows(g.allowed_time_windows)}
                      {g.revoked_at && " · ĐÃ THU HỒI"}
                    </p>
                  </div>
                  {!g.revoked_at && (
                    <button
                      type="button"
                      onClick={() => revoke(g.id)}
                      className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-2.5 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-800 dark:hover:bg-rose-950"
                    >
                      <Trash2 className="h-3 w-3" /> Thu hồi
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// -------------------------------------------------------- class-access tab
function ClassAccessTab({ classes, devices }: { classes: Cls[]; devices: Device[] }) {
  const deviceName = useMemo(
    () => Object.fromEntries(devices.map((d) => [d.id, d.name])),
    [devices],
  );
  const [classId, setClassId] = useState("");
  const [rows, setRows] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [deviceId, setDeviceId] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [windows, setWindows] = useState<TimeWindow[]>([]);
  const [weekly, setWeekly] = useState("20");

  const load = useCallback((cid: string) => {
    if (!cid) return setRows([]);
    setLoading(true);
    fetch(`${API}/classes/${cid}/devices`, { credentials: "include" })
      .then(j)
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => load(classId), [classId, load]);

  const create = async () => {
    if (!deviceId || !validFrom || !validTo) return alert("Chọn thiết bị + thời hạn.");
    const r = await fetch(`${API}/classes/${classId}/devices`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        valid_from: dayToIso(validFrom),
        valid_to: dayEndToIso(validTo),
        allowed_time_windows: windows,
        per_student_weekly_hours: Number(weekly) || 20,
        per_student_max_concurrent: 1,
        per_student_max_advance_days: 14,
      }),
    });
    if (r.ok) {
      setShowAdd(false);
      setDeviceId("");
      setWindows([]);
      load(classId);
    } else alert(`Gán thất bại: ${await errText(r)}`);
  };

  const revoke = async (id: string) => {
    if (!confirm("Thu hồi quyền lớp với thiết bị này?")) return;
    const r = await fetch(`${API}/classes/${classId}/devices/${id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (r.ok) load(classId);
    else alert(`Thu hồi lỗi: ${await errText(r)}`);
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
              <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
            ))}
          </select>
        </Field>
        {classId && (
          <button
            type="button"
            onClick={() => setShowAdd((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white"
          >
            <Plus className="h-4 w-4" /> {showAdd ? "Đóng" : "Gán thiết bị cho lớp"}
          </button>
        )}
      </div>

      {showAdd && classId && (
        <div className="surface grid gap-3 p-5 md:grid-cols-2">
          <Field label="Thiết bị">
            <select
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">— chọn thiết bị —</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>{d.name} ({d.device_type})</option>
              ))}
            </select>
          </Field>
          <TextInput label="Giờ/tuần mỗi SV" type="number" value={weekly} onChange={setWeekly} />
          <TextInput label="Hiệu lực từ" type="date" value={validFrom} onChange={setValidFrom} />
          <TextInput label="Hiệu lực đến" type="date" value={validTo} onChange={setValidTo} />
          <div className="md:col-span-2">
            <WeeklyWindowEditor windows={windows} onChange={setWindows} />
          </div>
          <button type="button" onClick={create} className="md:col-span-2 rounded-md bg-vju-500 px-4 py-2 text-sm font-semibold text-white">
            Gán cho lớp
          </button>
        </div>
      )}

      {!classId ? (
        <div className="surface p-10 text-center text-sm text-slate-500">
          Chọn lớp để xem &amp; gán thiết bị cho cả lớp.
        </div>
      ) : loading ? (
        <div className="surface h-24 animate-pulse" />
      ) : rows.length === 0 ? (
        <div className="surface p-10 text-center text-sm text-slate-500">Lớp này chưa gán thiết bị.</div>
      ) : (
        <ul className="space-y-2">
          {rows.map((a) => (
            <li key={a.id} className="surface flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <p className="font-semibold">{deviceName[a.device_id] ?? a.device_id}</p>
                <p className="text-xs text-slate-500">
                  {fmtDate(a.valid_from)}–{fmtDate(a.valid_to)} · {fmtWindows(a.allowed_time_windows)} ·{" "}
                  {a.per_student_weekly_hours}h/tuần
                </p>
              </div>
              <button
                type="button"
                onClick={() => revoke(a.id)}
                className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-800 dark:hover:bg-rose-950"
              >
                <Trash2 className="h-3 w-3" /> Thu hồi
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// -------------------------------------------------------------------- shell
function AccessInner() {
  const { user } = useUser();
  const [tab, setTab] = useState<"student" | "class">("student");
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
        <h1 className="text-3xl font-bold tracking-tight">Cấp quyền sử dụng thiết bị</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Chọn sinh viên + cấp thiết bị và khung giờ dùng hàng tuần.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        <TabButton active={tab === "student"} onClick={() => setTab("student")} icon={<Users className="h-4 w-4" />}>
          Cấp cho sinh viên
        </TabButton>
        <TabButton active={tab === "class"} onClick={() => setTab("class")} icon={<KeyRound className="h-4 w-4" />}>
          Cấp cho cả lớp
        </TabButton>
      </div>

      {tab === "student" ? (
        <StudentGrantTab classes={classes} devices={devices} />
      ) : (
        <ClassAccessTab classes={classes} devices={devices} />
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
