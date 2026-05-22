"use client";

import { ChevronDown, ChevronRight, ListChecks, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Cls = { id: string; code: string; name: string; semester: string };
type Student = { id: string; email: string; full_name: string; student_code: string | null };
type Enrollment = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  student_code: string | null;
};

const j = (r: Response) => (r.ok ? r.json() : Promise.reject(r));
async function errText(r: Response) {
  const e = await r.json().catch(() => ({}));
  return e?.detail?.code ?? `HTTP ${r.status}`;
}

// ----------------------------------------------------- per-class enrollment
function ManageStudents({ classId }: { classId: string }) {
  const [enrolled, setEnrolled] = useState<Enrollment[]>([]);
  const [roster, setRoster] = useState<Student[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/classes/${classId}/enrollments`, { credentials: "include" }).then(j),
      fetch(`${API}/teacher/students`, { credentials: "include" }).then(j),
    ])
      .then(([e, s]) => {
        setEnrolled(e);
        setRoster(s);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [classId]);
  useEffect(load, [load]);

  const enrolledIds = useMemo(() => new Set(enrolled.map((e) => e.user_id)), [enrolled]);
  const available = roster.filter((s) => !enrolledIds.has(s.id));

  const toggle = (id: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const enroll = async () => {
    if (picked.size === 0) return;
    const r = await fetch(`${API}/classes/${classId}/enroll`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_ids: [...picked] }),
    });
    if (r.ok) {
      setPicked(new Set());
      setShowAdd(false);
      load();
    } else alert(`Thêm thất bại: ${await errText(r)}`);
  };

  const unenroll = async (userId: string) => {
    if (!confirm("Xoá sinh viên này khỏi lớp?")) return;
    const r = await fetch(`${API}/classes/${classId}/enroll/${userId}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (r.ok) load();
    else alert(`Xoá thất bại: ${await errText(r)}`);
  };

  if (loading) return <div className="h-16 animate-pulse rounded-md bg-slate-100 dark:bg-slate-800" />;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-500">
          {enrolled.length} sinh viên trong lớp
        </p>
        <button
          type="button"
          onClick={() => setShowAdd((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md bg-vju-500 px-3 py-1.5 text-xs font-semibold text-white"
        >
          <UserPlus className="h-3 w-3" /> {showAdd ? "Đóng" : "Thêm sinh viên"}
        </button>
      </div>

      {showAdd && (
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
          <p className="mb-2 text-xs font-semibold text-slate-500">
            Chọn từ danh sách tài khoản sinh viên ({available.length} chưa trong lớp):
          </p>
          <div className="max-h-56 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700">
            {available.length === 0 ? (
              <p className="p-3 text-center text-xs text-slate-500">
                Mọi sinh viên đã ở trong lớp.
              </p>
            ) : (
              available.map((s) => (
                <label
                  key={s.id}
                  className="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-sm last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                >
                  <input type="checkbox" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
                  <span className="flex-1">
                    {s.full_name}{" "}
                    <span className="text-xs text-slate-500">{s.student_code ?? s.email}</span>
                  </span>
                </label>
              ))
            )}
          </div>
          <button
            type="button"
            onClick={enroll}
            disabled={picked.size === 0}
            className="mt-2 rounded-md bg-vju-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            Thêm {picked.size} sinh viên vào lớp
          </button>
        </div>
      )}

      {enrolled.length === 0 ? (
        <p className="text-xs text-slate-500">Lớp chưa có sinh viên.</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
          {enrolled.map((e) => (
            <li key={e.id} className="flex items-center justify-between px-3 py-1.5 text-sm">
              <span>
                {e.full_name}{" "}
                <span className="text-xs text-slate-500">{e.student_code ?? e.email}</span>
              </span>
              <button
                type="button"
                onClick={() => unenroll(e.user_id)}
                className="text-rose-500 hover:text-rose-700"
                aria-label="Xoá khỏi lớp"
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ----------------------------------------------------------------- page
function ClassesInner() {
  const { user } = useUser();
  const [classes, setClasses] = useState<Cls[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/classes`, { credentials: "include" })
      .then(j)
      .then(setClasses)
      .catch(() => setClasses([]))
      .finally(() => setLoading(false));
  }, []);

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl p-10 surface">Cần lecturer/admin.</div>;
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-10 md:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Lớp học &amp; sinh viên</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {classes.length} lớp · bấm vào lớp để quản lý danh sách sinh viên.
        </p>
      </div>

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : classes.length === 0 ? (
        <div className="surface p-12 text-center">
          <ListChecks className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">
            Chưa có lớp. Lớp được tạo qua seed/admin — liên hệ quản trị hệ thống.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {classes.map((c) => {
            const open = expanded === c.id;
            return (
              <li key={c.id} className="surface overflow-hidden">
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : c.id)}
                  className="flex w-full items-center justify-between gap-3 p-5 text-left"
                >
                  <div>
                    <p className="font-mono text-xs uppercase text-slate-500">{c.code}</p>
                    <p className="text-base font-semibold">{c.name}</p>
                    <p className="text-xs text-slate-500">{c.semester}</p>
                  </div>
                  {open ? (
                    <ChevronDown className="h-5 w-5 text-slate-400" />
                  ) : (
                    <ChevronRight className="h-5 w-5 text-slate-400" />
                  )}
                </button>
                {open && (
                  <div className="border-t border-slate-200 p-5 dark:border-slate-800">
                    <ManageStudents classId={c.id} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <p className="text-xs text-slate-500">
        ⓘ Admin tạo tài khoản sinh viên ở trang <strong>Người dùng</strong>. Giảng viên chọn sinh
        viên từ danh sách đó để thêm vào lớp, rồi cấp quyền thiết bị ở trang <strong>Quản lý
        quyền</strong>.
      </p>
    </div>
  );
}

export default function AdminClassesPage() {
  return (
    <AuthGate>
      <ClassesInner />
    </AuthGate>
  );
}
