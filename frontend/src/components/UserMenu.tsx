"use client";

import Link from "next/link";
import { LogOut, User as UserIcon, ChevronDown, ShieldCheck, Settings } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { logoutUrl, useUser } from "@/lib/auth";
import { L } from "@/components/LocaleText";

const ROLE_BADGE: Record<string, string> = {
  admin: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-100",
  lecturer: "bg-vju-100 text-vju-700 dark:bg-vju-900/40 dark:text-vju-100",
  ta: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-100",
  student: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-100",
};

export function UserMenu() {
  const { user, loading } = useUser();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  if (loading) {
    return <div className="h-8 w-20 animate-pulse rounded-md bg-slate-200 dark:bg-slate-800" />;
  }

  if (!user) {
    return (
      <Link
        href="/login"
        className="ml-1 hidden items-center gap-1.5 rounded-md bg-vju-500 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-vju-600 md:inline-flex"
      >
        <ShieldCheck className="h-4 w-4" />
        <L k="nav.login" />
      </Link>
    );
  }

  const initial = (user.full_name || user.email)[0]?.toUpperCase() ?? "?";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-vju-500 to-vju-700 text-sm font-semibold text-white">
          {initial}
        </span>
        <span className="hidden max-w-[140px] truncate md:inline">
          {user.full_name}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <p className="text-sm font-semibold">{user.full_name}</p>
            <p className="font-mono text-xs text-slate-500">{user.email}</p>
            <div className="mt-1.5 flex items-center gap-2">
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                  ROLE_BADGE[user.role] ?? ""
                }`}
              >
                {user.role}
              </span>
              {user.student_code && (
                <p className="font-mono text-[11px] text-slate-400">{user.student_code}</p>
              )}
            </div>
          </div>
          <Link
            href="/dashboard"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <UserIcon className="h-4 w-4" />
            <L k="nav.dashboard" />
          </Link>
          {(user.role === "admin" || user.role === "lecturer") && (
            <Link
              href="/admin"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <Settings className="h-4 w-4" />
              Quản trị
            </Link>
          )}
          <Link
            href="/change-password"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 border-t border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <Settings className="h-4 w-4" />
            Đổi mật khẩu
          </Link>
          <button
            type="button"
            onClick={async () => {
              await fetch(logoutUrl(), { method: "POST", credentials: "include" });
              window.location.href = "/login";
            }}
            className="flex w-full items-center gap-2 border-t border-slate-200 px-4 py-2 text-left text-sm text-rose-600 hover:bg-rose-50 dark:border-slate-700 dark:text-rose-400 dark:hover:bg-rose-950/30"
          >
            <LogOut className="h-4 w-4" />
            <L k="nav.logout" />
          </button>
        </div>
      )}
    </div>
  );
}
