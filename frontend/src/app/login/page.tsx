"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn, ShieldCheck, Loader2, AlertCircle, Wrench, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";

export const dynamic = "force-dynamic";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export default function LoginPage() {
  const router = useRouter();
  const [next, setNext] = useState("/dashboard");
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("next");
    if (p) setNext(p);
  }, []);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devEnabled, setDevEnabled] = useState(false);
  const [devBusy, setDevBusy] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/auth/dev-status`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { enabled: false }))
      .then((d) => setDevEnabled(Boolean(d.enabled)))
      .catch(() => setDevEnabled(false));
  }, []);

  const devLogin = async (role: "admin" | "lecturer" | "student") => {
    setDevBusy(role);
    setError(null);
    try {
      const r = await fetch(`${API}/auth/dev-login/${role}`, {
        method: "POST",
        credentials: "include",
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        setError(`Dev-login lỗi: ${e?.detail?.code ?? r.status}`);
        setDevBusy(null);
        return;
      }
      router.replace(next);
    } catch (e) {
      setError(`Lỗi mạng: ${e}`);
      setDevBusy(null);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        const code = e?.detail?.code ?? "ERROR";
        setError(
          code === "INVALID_CREDENTIALS"
            ? "Email hoặc mật khẩu không đúng."
            : `Lỗi: ${code}`,
        );
        setSubmitting(false);
        return;
      }
      const me = await r.json();
      if (me.must_change_password) {
        router.replace(`/change-password?next=${encodeURIComponent(next)}`);
      } else {
        router.replace(next);
      }
    } catch (e) {
      setError(`Lỗi mạng: ${e}`);
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-8 px-4 py-16 md:py-24">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-vju-500 to-vju-700 text-white shadow-md">
        <ShieldCheck className="h-7 w-7" />
      </div>
      <div className="space-y-2 text-center">
        <h1 className="text-3xl font-bold tracking-tight md:text-4xl">Đăng nhập</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Dùng tài khoản BCSE Identity (1 tài khoản, mọi cổng hệ sinh thái BCSE).
        </p>
      </div>

      <a
        href={`${API}/auth/sso/authorize?returnTo=${encodeURIComponent(next)}`}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:from-indigo-600 hover:to-violet-700"
      >
        <KeyRound className="h-4 w-4" />
        Đăng nhập qua BCSE Identity (SSO)
      </a>

      <div className="flex w-full items-center gap-3 text-xs text-slate-400 dark:text-slate-500">
        <span className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        <span>hoặc đăng nhập bằng mật khẩu cục bộ</span>
        <span className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
      </div>

      <form onSubmit={submit} className="surface w-full space-y-4 p-6">
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Email VJU
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ten@st.vju.ac.vn hoặc ten@vju.ac.vn"
            required
            autoFocus
            autoComplete="email"
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Mật khẩu
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !email || !password}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-vju-500 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-vju-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
          Đăng nhập
        </button>

        <p className="text-center text-xs text-slate-500 dark:text-slate-400">
          Chưa có tài khoản? Liên hệ admin (<code>admin@vju.ac.vn</code>) để được cấp.
        </p>
      </form>

      {devEnabled && (
        <div className="surface w-full space-y-3 border-amber-300 bg-amber-50/60 p-5 dark:border-amber-800 dark:bg-amber-950/20">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-amber-700 dark:text-amber-400">
            <Wrench className="h-4 w-4" />
            Chế độ Dev — đăng nhập nhanh để kiểm thử
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Click để vào thẳng dashboard theo từng vai trò. Tắt khi chạy thật
            (DEV_LOGIN_ENABLED=false) — khi đó chỉ còn login whitelist.
          </p>
          <div className="grid grid-cols-3 gap-2">
            {(["admin", "lecturer", "student"] as const).map((role) => (
              <button
                key={role}
                type="button"
                onClick={() => devLogin(role)}
                disabled={devBusy !== null}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-2 text-xs font-semibold capitalize text-amber-800 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-800 dark:bg-slate-900 dark:text-amber-300 dark:hover:bg-slate-800"
              >
                {devBusy === role ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : null}
                {role === "lecturer" ? "Giảng viên" : role === "student" ? "Sinh viên" : "Admin"}
              </button>
            ))}
          </div>
        </div>
      )}

      <Link
        href="/"
        className="text-sm font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      >
        ← Trang chủ
      </Link>
    </div>
  );
}
