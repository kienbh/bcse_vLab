"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn, ShieldCheck, Loader2, AlertCircle } from "lucide-react";
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
    <div className="mx-auto flex max-w-md flex-col gap-5 px-4 py-10 md:py-14">
      {/* Hero banner — cinematic Kria rack with title overlay */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-200 shadow-md dark:border-slate-700">
        <img
          src="/images/lab-hero-cinematic.png"
          alt=""
          aria-hidden="true"
          className="h-44 w-full object-cover md:h-52"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-950/85 via-slate-950/40 to-slate-950/10" />
        <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-white/15 text-white shadow-sm backdrop-blur-sm">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-white drop-shadow md:text-4xl">
            Đăng nhập
          </h1>
        </div>
      </div>
      <p className="text-center text-sm text-slate-600 dark:text-slate-400">
        Dùng email VJU đã được cấp + mật khẩu mặc định{" "}
        <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs dark:bg-slate-800">
          VJU@2026
        </code>
        . Lần đầu đăng nhập, hệ thống sẽ yêu cầu đổi mật khẩu.
      </p>

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

      <Link
        href="/"
        className="text-sm font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      >
        ← Trang chủ
      </Link>
    </div>
  );
}
