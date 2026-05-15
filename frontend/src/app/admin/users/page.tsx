"use client";

import { Plus, RotateCcw, X, Users as UsersIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Role = "student" | "ta" | "lecturer" | "admin";

type AdminUser = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  student_code: string | null;
  is_active: boolean;
  must_change_password: boolean;
};

const ROLE_BADGE: Record<Role, string> = {
  admin: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-100",
  lecturer: "bg-vju-100 text-vju-700 dark:bg-vju-900/40 dark:text-vju-100",
  ta: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-100",
  student: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-100",
};

function UsersAdminInner() {
  const { user } = useUser();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState<{
    email: string;
    full_name: string;
    role: Role;
    student_code: string;
  }>({ email: "", full_name: "", role: "student", student_code: "" });
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null);

  const refresh = () => {
    setLoading(true);
    fetch(`${API}/auth/admin/users`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        setUsers(d);
        setLoading(false);
      });
  };

  useEffect(refresh, []);

  if (!user || user.role !== "admin") {
    return <div className="mx-auto max-w-3xl p-10 surface">Trang này chỉ dành cho admin.</div>;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    const r = await fetch(`${API}/auth/admin/users`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: form.email.trim().toLowerCase(),
        full_name: form.full_name.trim(),
        role: form.role,
        student_code: form.student_code.trim() || null,
      }),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      setFeedback({
        ok: true,
        msg: `✓ Tạo ${d.email} (${d.role}) thành công. Mật khẩu ban đầu: ${d.initial_password}`,
      });
      setForm({ email: "", full_name: "", role: "student", student_code: "" });
      refresh();
    } else {
      setFeedback({
        ok: false,
        msg: `✗ ${d?.detail?.code ?? "ERROR"}: ${JSON.stringify(d?.detail ?? d)}`,
      });
    }
  };

  const resetPassword = async (u: AdminUser) => {
    if (!confirm(`Reset mật khẩu cho ${u.email} về VJU@2026?`)) return;
    const r = await fetch(`${API}/auth/admin/users/${u.id}/reset-password`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      alert(`✓ Reset OK. Mật khẩu mới: ${d.new_password}\nNgười dùng phải đổi khi đăng nhập lần kế tiếp.`);
    } else {
      alert(`✗ ${JSON.stringify(d)}`);
    }
  };

  const changeRole = async (u: AdminUser, newRole: Role) => {
    const r = await fetch(`${API}/auth/admin/users/${u.id}/role?role=${newRole}`, {
      method: "PATCH",
      credentials: "include",
    });
    if (r.ok) refresh();
    else alert("Không đổi role được.");
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <AdminPageHeader
        title="Quản lý người dùng"
        subtitle={`${users.length} tài khoản`}
        actions={
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white"
          >
            {show ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {show ? "Đóng" : "Tạo tài khoản"}
          </button>
        }
      />

      {show && (
        <form onSubmit={submit} className="surface grid gap-3 p-5 md:grid-cols-2">
          <Input
            label="Email"
            type="email"
            value={form.email}
            onChange={(v) => setForm({ ...form, email: v })}
            placeholder="ten@st.vju.ac.vn"
          />
          <Input
            label="Họ tên"
            value={form.full_name}
            onChange={(v) => setForm({ ...form, full_name: v })}
            placeholder="Nguyễn Văn A"
          />
          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
            Role
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              <option value="student">Student</option>
              <option value="ta">TA</option>
              <option value="lecturer">Lecturer</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <Input
            label="Student code (optional)"
            value={form.student_code}
            onChange={(v) => setForm({ ...form, student_code: v })}
            placeholder="BCSE2024xxx"
            required={false}
          />
          <button
            type="submit"
            className="md:col-span-2 rounded-md bg-vju-500 px-4 py-2 text-sm font-semibold text-white hover:bg-vju-600"
          >
            Tạo (mật khẩu mặc định: <code>VJU@2026</code>)
          </button>
          {feedback && (
            <div
              className={`md:col-span-2 rounded-md border p-3 text-xs ${
                feedback.ok
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200"
                  : "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200"
              }`}
            >
              {feedback.msg}
            </div>
          )}
        </form>
      )}

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : users.length === 0 ? (
        <div className="surface p-12 text-center">
          <UsersIcon className="mx-auto h-10 w-10 text-slate-300" />
        </div>
      ) : (
        <div className="surface overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-800/50">
              <tr>
                <th className="px-5 py-3 text-left">Email</th>
                <th className="px-5 py-3 text-left">Họ tên</th>
                <th className="px-5 py-3 text-left">Role</th>
                <th className="px-5 py-3 text-left">Mã SV</th>
                <th className="px-5 py-3 text-left">Trạng thái</th>
                <th className="px-5 py-3 text-right">Hành động</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-5 py-3 font-mono text-xs">{u.email}</td>
                  <td className="px-5 py-3">{u.full_name}</td>
                  <td className="px-5 py-3">
                    <select
                      value={u.role}
                      onChange={(e) => changeRole(u, e.target.value as Role)}
                      className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${ROLE_BADGE[u.role]}`}
                    >
                      <option value="student">student</option>
                      <option value="ta">ta</option>
                      <option value="lecturer">lecturer</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="px-5 py-3 font-mono text-xs">{u.student_code ?? "—"}</td>
                  <td className="px-5 py-3 text-xs">
                    {u.must_change_password ? (
                      <span className="text-amber-600">⚠ chưa đổi mk</span>
                    ) : (
                      <span className="text-emerald-600">✓ active</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => resetPassword(u)}
                      className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
                      title="Reset password về VJU@2026"
                    >
                      <RotateCcw className="h-3 w-3" />
                      Reset
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Input({
  label, value, onChange, type = "text", placeholder, required = true,
}: {
  label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; required?: boolean;
}) {
  return (
    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </label>
  );
}

export default function AdminUsersPage() {
  return (
    <AuthGate>
      <UsersAdminInner />
    </AuthGate>
  );
}
