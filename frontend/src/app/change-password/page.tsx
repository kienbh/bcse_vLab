"use client";

import { useRouter } from "next/navigation";
import { KeyRound, Loader2, AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function ChangeInner() {
  const router = useRouter();
  const [next, setNext] = useState("/dashboard");
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("next");
    if (p) setNext(p);
  }, []);
  const { user, refresh } = useUser();
  const [current, setCurrent] = useState("");
  const [next1, setNext1] = useState("");
  const [next2, setNext2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next1 !== next2) {
      setError("Hai ô mật khẩu mới không khớp.");
      return;
    }
    if (next1.length < 8) {
      setError("Mật khẩu mới phải tối thiểu 8 ký tự.");
      return;
    }
    if (next1 === current) {
      setError("Mật khẩu mới phải khác mật khẩu hiện tại.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await fetch(`${API}/auth/change-password`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next1 }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        const code = e?.detail?.code ?? "ERROR";
        setError(
          code === "WRONG_CURRENT_PASSWORD"
            ? "Mật khẩu hiện tại không đúng."
            : code === "SAME_AS_OLD"
              ? "Mật khẩu mới phải khác mật khẩu cũ."
              : `Lỗi: ${code}`,
        );
        setSubmitting(false);
        return;
      }
      refresh();
      router.replace(next);
    } catch (e) {
      setError(`Lỗi mạng: ${e}`);
      setSubmitting(false);
    }
  };

  if (!user) return null;
  const forced = user.must_change_password;

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 px-4 py-12 md:py-20">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-amber-500 to-amber-700 text-white shadow-md">
        <KeyRound className="h-7 w-7" />
      </div>
      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
          {forced ? "Đổi mật khẩu lần đầu" : "Đổi mật khẩu"}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {forced ? (
            <>
              Tài khoản <span className="font-semibold">{user.email}</span> đang dùng mật khẩu mặc định.
              Đổi mật khẩu để tiếp tục.
            </>
          ) : (
            <>Đặt mật khẩu mới cho <span className="font-semibold">{user.email}</span>.</>
          )}
        </p>
      </div>

      <form onSubmit={submit} className="surface w-full space-y-3 p-6">
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Mật khẩu hiện tại
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            autoFocus
            autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Mật khẩu mới (≥ 8 ký tự)
          <input
            type="password"
            value={next1}
            onChange={(e) => setNext1(e.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Nhập lại mật khẩu mới
          <input
            type="password"
            value={next2}
            onChange={(e) => setNext2(e.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
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
          disabled={submitting}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-vju-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-vju-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Đổi mật khẩu
        </button>
      </form>
    </div>
  );
}

export default function ChangePasswordPage() {
  return (
    <AuthGate>
      <ChangeInner />
    </AuthGate>
  );
}
