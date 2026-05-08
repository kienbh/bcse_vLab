"use client";

import { useEffect, useState } from "react";

import type { Locale } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export function Footer() {
  const [locale, setLocale] = useState<Locale>("vi");
  useEffect(() => {
    const saved = localStorage.getItem("locale") as Locale | null;
    if (saved === "vi" || saved === "en") setLocale(saved);
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<Locale>).detail;
      if (detail === "vi" || detail === "en") setLocale(detail);
    };
    window.addEventListener("locale-changed", handler);
    return () => window.removeEventListener("locale-changed", handler);
  }, []);

  return (
    <footer className="mt-auto border-t border-slate-200/60 py-8 text-center text-xs text-slate-500 dark:border-slate-800/60 dark:text-slate-500">
      <p>{t(locale, "footer.note", { year: String(new Date().getFullYear()) })}</p>
      <p className="mt-1 font-mono text-[11px] opacity-60">M0 bootstrap · ADR-0011 · sv14.bcse-vju.com</p>
    </footer>
  );
}
