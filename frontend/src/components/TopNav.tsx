"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Cpu, Calendar, CalendarDays, KeyRound, LayoutDashboard, Globe, Moon, Sun, Menu, X, Cog, Zap, Server } from "lucide-react";

import { ResetQueueBadge } from "@/components/ResetQueueBadge";
import { UserMenu } from "@/components/UserMenu";
import type { Locale, MessageKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";

function useLocale(): [Locale, (l: Locale) => void] {
  const [locale, setLocale] = useState<Locale>("vi");
  useEffect(() => {
    const saved = (typeof window !== "undefined" && localStorage.getItem("locale")) as Locale | null;
    if (saved === "vi" || saved === "en") setLocale(saved);
  }, []);
  const change = (l: Locale) => {
    setLocale(l);
    if (typeof window !== "undefined") {
      localStorage.setItem("locale", l);
      window.dispatchEvent(new CustomEvent("locale-changed", { detail: l }));
    }
  };
  return [locale, change];
}

function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const useDark = saved === "dark" || (saved == null && prefersDark);
    setDark(useDark);
    document.documentElement.classList.toggle("dark", useDark);
  }, []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };
  return [dark, toggle];
}

export function TopNav() {
  const path = usePathname();
  const [locale, setLocale] = useLocale();
  const [dark, toggleTheme] = useTheme();
  const [open, setOpen] = useState(false);

  const tr = (k: MessageKey) => t(locale, k);

  const items = [
    { href: "/", label: tr("nav.home"), icon: null },
    { href: "/devices/fpga", label: "FPGA", icon: <Cog className="h-4 w-4" /> },
    { href: "/devices/jetson", label: "Jetson", icon: <Cpu className="h-4 w-4" /> },
    { href: "/devices/rpi", label: "Pi", icon: <Zap className="h-4 w-4" /> },
    { href: "/devices/vps", label: "VPS", icon: <Server className="h-4 w-4" /> },
    { href: "/vps-access", label: "Quyền VPS", icon: <KeyRound className="h-4 w-4" /> },
    { href: "/schedule", label: "Lịch nhóm", icon: <CalendarDays className="h-4 w-4" /> },
    { href: "/bookings", label: tr("nav.bookings"), icon: <Calendar className="h-4 w-4" /> },
    { href: "/dashboard", label: tr("nav.dashboard"), icon: <LayoutDashboard className="h-4 w-4" /> },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/60 bg-white/80 backdrop-blur-md dark:border-slate-800/60 dark:bg-slate-950/70">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 md:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight shrink-0">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-vju-500 to-vju-700 text-white shadow-sm">
            <Cpu className="h-4 w-4" />
          </div>
          <span className="hidden lg:inline">VJU Lab Portal</span>
        </Link>

        <nav className="hidden flex-1 items-center gap-1 md:flex">
          {items.slice(1).map((it) => {
            const active = path === it.href;
            return (
              <Link
                key={it.href}
                href={it.href}
                className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] font-medium transition ${
                  active
                    ? "bg-vju-50 text-vju-700 dark:bg-vju-900/40 dark:text-vju-100"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
                }`}
              >
                {it.icon}
                <span className="hidden xl:inline">{it.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => setLocale(locale === "vi" ? "en" : "vi")}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-semibold uppercase text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Toggle language"
          >
            <Globe className="h-4 w-4" />
            <span className="hidden sm:inline">{locale}</span>
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex items-center rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Toggle theme"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <ResetQueueBadge />
          <UserMenu />
          <button
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 md:hidden"
            onClick={() => setOpen((o) => !o)}
            aria-label="Toggle menu"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="border-t border-slate-200 bg-white px-4 py-2 dark:border-slate-800 dark:bg-slate-950 md:hidden">
          {items.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {it.icon}
              {it.label}
            </Link>
          ))}
          <a
            href="/api/auth/login"
            onClick={() => setOpen(false)}
            className="mt-1 flex items-center gap-2 rounded-md bg-vju-500 px-3 py-2 text-sm font-semibold text-white"
          >
            {tr("nav.login")}
          </a>
        </nav>
      )}
    </header>
  );
}
