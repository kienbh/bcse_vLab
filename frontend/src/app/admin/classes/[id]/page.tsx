"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  CalendarDays,
  Crown,
  ListChecks,
  Plus,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type ClassT = { id: string; code: string; name: string; semester: string };
type RosterRow = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  student_code: string | null;
  group_id: string | null;
  group_name: string | null;
};
type Member = { user_id: string; email: string; full_name: string; is_leader: boolean };
type GroupT = {
  id: string;
  class_id: string;
  name: string;
  leader_id: string | null;
  members: Member[];
};
type SlotT = {
  id: string;
  device_id: string;
  device_name: string;
  group_id: string;
  group_name: string;
  day_of_week: number;
  time_slot: string;
};
type DeviceT = { id: string; name: string };

type ActFn = (fn: () => Promise<unknown>) => Promise<void>;

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
  { v: "morning", label: "Sáng (08–12)" },
  { v: "afternoon", label: "Chiều (13–17)" },
  { v: "evening", label: "Tối (18–22)" },
];

async function j(url: string, opts?: RequestInit): Promise<unknown> {
  const r = await fetch(url, { credentials: "include", ...opts });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e?.detail?.hint || e?.detail?.code || `HTTP ${r.status}`);
  }
  return r.json().catch(() => ({}));
}

// ---------------------------------------------------------------- shared bits

function Field({
  label,
  value,
  onChange,
  placeholder,
  wide,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  wide?: boolean;
}) {
  return (
    <label
      className={`block text-xs font-semibold text-slate-600 dark:text-slate-400 ${
        wide ? "min-w-[200px] flex-1" : ""
      }`}
    >
      {label}
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------- roster

function RosterSection({
  classId,
  roster,
  act,
}: {
  classId: string;
  roster: RosterRow[];
  act: ActFn;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");

  return (
    <div className="flex flex-col gap-4">
      <div className="surface flex flex-wrap items-end gap-2 p-4">
        <Field label="Email SV" value={email} onChange={setEmail} placeholder="sv@st.vju.ac.vn" wide />
        <Field label="Họ tên (tùy chọn)" value={name} onChange={setName} />
        <Field label="MSSV (tùy chọn)" value={code} onChange={setCode} />
        <button
          type="button"
          disabled={!email}
          onClick={() =>
            act(async () => {
              await j(`${API}/classes/${classId}/enroll`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  email,
                  full_name: name || null,
                  student_code: code || null,
                }),
              });
              setEmail("");
              setName("");
              setCode("");
            })
          }
          className="inline-flex items-center gap-1 rounded-md bg-vju-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <UserPlus className="h-4 w-4" /> Thêm SV
        </button>
      </div>

      <div className="surface overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500 dark:bg-slate-900">
            <tr>
              <th className="p-3">Email</th>
              <th className="p-3">Họ tên</th>
              <th className="p-3">MSSV</th>
              <th className="p-3">Nhóm</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {roster.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-slate-400">
                  Chưa có sinh viên nào.
                </td>
              </tr>
            ) : (
              roster.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="p-3">{r.email}</td>
                  <td className="p-3">{r.full_name}</td>
                  <td className="p-3 text-slate-500">{r.student_code || "—"}</td>
                  <td className="p-3">
                    {r.group_name ? (
                      <span className="rounded bg-vju-50 px-2 py-0.5 text-xs font-semibold text-vju-700 dark:bg-vju-900/40 dark:text-vju-200">
                        {r.group_name}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">— chưa có nhóm</span>
                    )}
                  </td>
                  <td className="p-3 text-right">
                    <button
                      type="button"
                      onClick={() =>
                        act(() =>
                          j(`${API}/classes/${classId}/enrollments/${r.id}`, { method: "DELETE" }),
                        )
                      }
                      className="text-rose-500 hover:text-rose-700"
                      aria-label="Xóa SV"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400">
        ⓘ Email phải <code>@st.vju.ac.vn</code> / <code>@vju.ac.vn</code>. SV mới sẽ tự tạo tài khoản
        (mật khẩu mặc định <code>VJU@2026</code>).
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- groups

function AddMember({
  classId,
  group,
  roster,
  act,
}: {
  classId: string;
  group: GroupT;
  roster: RosterRow[];
  act: ActFn;
}) {
  const [sel, setSel] = useState("");
  const inGroup = new Set(group.members.map((m) => m.user_id));
  const avail = roster.filter((r) => !inGroup.has(r.user_id));

  return (
    <div className="flex gap-2">
      <select
        value={sel}
        onChange={(e) => setSel(e.target.value)}
        className="flex-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
      >
        <option value="">+ Thêm SV vào nhóm…</option>
        {avail.map((r) => (
          <option key={r.user_id} value={r.user_id}>
            {r.full_name} ({r.email}){r.group_name ? ` — đang ở ${r.group_name}` : ""}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!sel}
        onClick={() =>
          act(async () => {
            await j(`${API}/classes/${classId}/groups/${group.id}/members`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ user_id: sel }),
            });
            setSel("");
          })
        }
        className="rounded-md bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300 dark:bg-slate-200 dark:text-slate-900"
      >
        Thêm
      </button>
    </div>
  );
}

function GroupsSection({
  classId,
  groups,
  roster,
  act,
}: {
  classId: string;
  groups: GroupT[];
  roster: RosterRow[];
  act: ActFn;
}) {
  const [newName, setNewName] = useState("");

  return (
    <div className="flex flex-col gap-4">
      <div className="surface flex items-end gap-2 p-4">
        <Field label="Tên nhóm mới" value={newName} onChange={setNewName} placeholder="Nhóm 1" wide />
        <button
          type="button"
          disabled={!newName}
          onClick={() =>
            act(async () => {
              await j(`${API}/classes/${classId}/groups`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: newName }),
              });
              setNewName("");
            })
          }
          className="inline-flex items-center gap-1 rounded-md bg-vju-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <Plus className="h-4 w-4" /> Tạo nhóm
        </button>
      </div>

      {groups.length === 0 && (
        <p className="text-sm text-slate-400">Chưa có nhóm — tạo nhóm rồi gán SV vào.</p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((g) => (
          <div key={g.id} className="surface flex flex-col gap-3 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{g.name}</h3>
              <button
                type="button"
                onClick={() =>
                  act(() => j(`${API}/classes/${classId}/groups/${g.id}`, { method: "DELETE" }))
                }
                className="text-rose-500 hover:text-rose-700"
                aria-label="Xóa nhóm"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="flex flex-col gap-1">
              {g.members.length === 0 && (
                <p className="text-xs text-slate-400">Chưa có thành viên.</p>
              )}
              {g.members.map((m) => (
                <div
                  key={m.user_id}
                  className="flex items-center justify-between gap-2 rounded bg-slate-50 px-2 py-1 text-xs dark:bg-slate-900"
                >
                  <span className="inline-flex items-center gap-1 truncate">
                    {m.is_leader && <Crown className="h-3 w-3 shrink-0 text-amber-500" />}
                    <span className="font-medium">{m.full_name}</span>
                    <span className="truncate text-slate-400">{m.email}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {!m.is_leader && (
                      <button
                        type="button"
                        onClick={() =>
                          act(() =>
                            j(`${API}/classes/${classId}/groups/${g.id}`, {
                              method: "PATCH",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ leader_id: m.user_id }),
                            }),
                          )
                        }
                        className="font-semibold text-amber-600 hover:underline"
                      >
                        Đặt trưởng
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() =>
                        act(() =>
                          j(`${API}/classes/${classId}/groups/${g.id}/members/${m.user_id}`, {
                            method: "DELETE",
                          }),
                        )
                      }
                      className="text-rose-500 hover:text-rose-700"
                      aria-label="Bỏ khỏi nhóm"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </span>
                </div>
              ))}
            </div>

            <AddMember classId={classId} group={g} roster={roster} act={act} />
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-400">
        ⓘ Mỗi SV thuộc 1 nhóm. Chỉ <b>nhóm trưởng</b> (👑) mới được connect kit + gửi đề xuất cho
        nhóm.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- weekly plan

function PlanSection({
  classId,
  slots,
  groups,
  devices,
  act,
}: {
  classId: string;
  slots: SlotT[];
  groups: GroupT[];
  devices: DeviceT[];
  act: ActFn;
}) {
  const [device, setDevice] = useState("");
  const [group, setGroup] = useState("");
  const [day, setDay] = useState("1");
  const [slot, setSlot] = useState("morning");

  const cell = (d: number, s: string) =>
    slots.filter((x) => x.day_of_week === d && x.time_slot === s);

  return (
    <div className="flex flex-col gap-4">
      <div className="surface flex flex-wrap items-end gap-2 p-4">
        <SelectField
          label="Kit"
          value={device}
          onChange={setDevice}
          options={[["", "— chọn kit —"], ...devices.map((d) => [d.id, d.name] as [string, string])]}
        />
        <SelectField
          label="Nhóm"
          value={group}
          onChange={setGroup}
          options={[["", "— chọn nhóm —"], ...groups.map((g) => [g.id, g.name] as [string, string])]}
        />
        <SelectField
          label="Thứ"
          value={day}
          onChange={setDay}
          options={DAYS.map((d) => [String(d.v), d.label] as [string, string])}
        />
        <SelectField
          label="Ca"
          value={slot}
          onChange={setSlot}
          options={SLOTS.map((s) => [s.v, s.label] as [string, string])}
        />
        <button
          type="button"
          disabled={!device || !group}
          onClick={() =>
            act(async () => {
              await j(`${API}/classes/${classId}/planned-slots`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  device_id: device,
                  group_id: group,
                  day_of_week: Number(day),
                  time_slot: slot,
                }),
              });
              setDevice("");
              setGroup("");
            })
          }
          className="inline-flex items-center gap-1 rounded-md bg-vju-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <Plus className="h-4 w-4" /> Gán
        </button>
      </div>

      <div className="surface overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
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
                {SLOTS.map((s) => (
                  <td key={s.v} className="p-2 align-top">
                    <div className="flex flex-col gap-1">
                      {cell(d.v, s.v).map((x) => (
                        <span
                          key={x.id}
                          className="inline-flex items-center justify-between gap-1 rounded bg-vju-50 px-2 py-0.5 text-xs dark:bg-vju-900/40"
                        >
                          <span className="truncate">
                            <b>{x.device_name}</b> → {x.group_name}
                          </span>
                          <button
                            type="button"
                            onClick={() =>
                              act(() =>
                                j(`${API}/classes/${classId}/planned-slots/${x.id}`, {
                                  method: "DELETE",
                                }),
                              )
                            }
                            className="shrink-0 text-rose-500 hover:text-rose-700"
                            aria-label="Xóa slot"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                      {cell(d.v, s.v).length === 0 && (
                        <span className="text-xs text-slate-300 dark:text-slate-600">—</span>
                      )}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400">
        ⓘ Mỗi ô (kit + thứ + ca) chỉ gán được 1 nhóm. Nhóm được cấp slot sẵn — tới giờ nhóm trưởng
        bấm Connect.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- page

function ManageInner() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { user } = useUser();
  const [tab, setTab] = useState<"roster" | "groups" | "plan">("roster");
  const [cls, setCls] = useState<ClassT | null>(null);
  const [roster, setRoster] = useState<RosterRow[]>([]);
  const [groups, setGroups] = useState<GroupT[]>([]);
  const [slots, setSlots] = useState<SlotT[]>([]);
  const [devices, setDevices] = useState<DeviceT[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const all = (await j(`${API}/classes`)) as ClassT[];
      setCls(all.find((c) => c.id === id) ?? null);
      setRoster((await j(`${API}/classes/${id}/enrollments`)) as RosterRow[]);
      setGroups((await j(`${API}/classes/${id}/groups`)) as GroupT[]);
      setSlots((await j(`${API}/classes/${id}/planned-slots`)) as SlotT[]);
      setDevices((await j(`${API}/devices`)) as DeviceT[]);
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl surface p-10">Cần lecturer/admin.</div>;
  }

  const act: ActFn = async (fn) => {
    setErr(null);
    try {
      await fn();
      await loadAll();
    } catch (e) {
      setErr(String(e));
    }
  };

  const tabs = [
    ["roster", "Sinh viên", Users],
    ["groups", "Nhóm", ListChecks],
    ["plan", "Lịch tuần", CalendarDays],
  ] as const;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-8 md:px-6">
      <Link
        href="/admin/classes"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
      >
        <ArrowLeft className="h-4 w-4" /> Tất cả lớp
      </Link>
      <div>
        <p className="font-mono text-xs uppercase text-slate-500">{cls?.code ?? "…"}</p>
        <h1 className="text-2xl font-bold tracking-tight">{cls?.name ?? "Đang tải…"}</h1>
      </div>

      {err && (
        <div className="surface border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {err}
        </div>
      )}

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {tabs.map(([k, label, Icon]) => (
          <button
            key={k}
            type="button"
            onClick={() => setTab(k)}
            className={`inline-flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-semibold transition ${
              tab === k
                ? "border-vju-500 text-vju-700 dark:text-vju-300"
                : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
            }`}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "roster" && <RosterSection classId={id} roster={roster} act={act} />}
      {tab === "groups" && (
        <GroupsSection classId={id} groups={groups} roster={roster} act={act} />
      )}
      {tab === "plan" && (
        <PlanSection classId={id} slots={slots} groups={groups} devices={devices} act={act} />
      )}
    </div>
  );
}

export default function ClassManagePage() {
  return (
    <AuthGate>
      <ManageInner />
    </AuthGate>
  );
}
