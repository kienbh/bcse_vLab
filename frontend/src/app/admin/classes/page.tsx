"use client";

import Link from "next/link";
import { ListChecks, Plus, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Class = {
  id: string;
  code: string;
  name: string;
  semester: string;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
};

function ClassesInner() {
  const { user } = useUser();
  const [classes, setClasses] = useState<Class[]>([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({
    code: "",
    name: "",
    semester: "2026-1",
    starts_at: "",
    ends_at: "",
  });

  const refresh = () => {
    setLoading(true);
    fetch(`${API}/classes`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        setClasses(d);
        setLoading(false);
      });
  };
  useEffect(refresh, []);

  if (!user || (user.role !== "admin" && user.role !== "lecturer")) {
    return <div className="mx-auto max-w-3xl p-10 surface">Cần lecturer/admin.</div>;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      ...form,
      starts_at: new Date(form.starts_at).toISOString(),
      ends_at: new Date(form.ends_at).toISOString(),
    };
    const r = await fetch(`${API}/classes`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) {
      setShow(false);
      setForm({ code: "", name: "", semester: "2026-1", starts_at: "", ends_at: "" });
      refresh();
    } else {
      const e = await r.json().catch(() => ({}));
      alert(`Tạo lớp thất bại: ${JSON.stringify(e)}`);
    }
  };

  const uploadCsv = async (classId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${API}/classes/${classId}/enroll/csv`, {
      method: "POST",
      credentials: "include",
      body: fd,
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      alert(
        `Enrolled: ${d.enrolled}, created users: ${d.created_users}, skipped: ${d.skipped?.length ?? 0}, errors: ${d.errors?.length ?? 0}`,
      );
    } else alert(`Lỗi: ${JSON.stringify(d)}`);
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Lớp học</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">{classes.length} lớp</p>
        </div>
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white"
        >
          <Plus className="h-4 w-4" />
          {show ? "Đóng" : "Tạo lớp"}
        </button>
      </header>

      {show && (
        <form onSubmit={submit} className="surface grid gap-3 p-5 md:grid-cols-2">
          <Input label="Mã lớp" value={form.code} onChange={(v) => setForm({ ...form, code: v })} placeholder="CIS3043-2026-01" />
          <Input label="Học kỳ" value={form.semester} onChange={(v) => setForm({ ...form, semester: v })} />
          <Input label="Tên lớp" value={form.name} onChange={(v) => setForm({ ...form, name: v })} className="md:col-span-2" />
          <Input
            label="Bắt đầu"
            type="datetime-local"
            value={form.starts_at}
            onChange={(v) => setForm({ ...form, starts_at: v })}
          />
          <Input
            label="Kết thúc"
            type="datetime-local"
            value={form.ends_at}
            onChange={(v) => setForm({ ...form, ends_at: v })}
          />
          <button type="submit" className="md:col-span-2 rounded-md bg-vju-500 px-4 py-2 text-sm font-semibold text-white">
            Tạo
          </button>
        </form>
      )}

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : classes.length === 0 ? (
        <div className="surface p-12 text-center">
          <ListChecks className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">Chưa có lớp nào.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {classes.map((c) => (
            <li key={c.id} className="surface flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-mono text-xs uppercase text-slate-500">{c.code}</p>
                <p className="text-base font-semibold">{c.name}</p>
                <p className="text-xs text-slate-500">
                  {c.semester} · {new Date(c.starts_at).toLocaleDateString("vi-VN")} →{" "}
                  {new Date(c.ends_at).toLocaleDateString("vi-VN")}
                </p>
              </div>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800">
                <Upload className="h-3 w-3" />
                Enroll CSV
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && uploadCsv(c.id, e.target.files[0])}
                />
              </label>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-slate-500">
        ⓘ CSV format: <code>email,full_name,student_code</code> — header optional. Email phải{" "}
        <code>@st.vju.ac.vn</code> hoặc <code>@vju.ac.vn</code>; user mới sẽ tự tạo.
      </p>
    </div>
  );
}

function Input({
  label, value, onChange, type = "text", placeholder, className = "",
}: { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; className?: string }) {
  return (
    <label className={`block text-xs font-semibold text-slate-600 dark:text-slate-400 ${className}`}>
      {label}
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        required
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </label>
  );
}

export default function AdminClassesPage() {
  return (
    <AuthGate>
      <ClassesInner />
    </AuthGate>
  );
}
