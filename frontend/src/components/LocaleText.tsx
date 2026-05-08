"use client";

import { useEffect, useState } from "react";

import type { Locale, MessageKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export function useLocaleListener(): Locale {
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
  return locale;
}

export function L({ k, vars }: { k: MessageKey; vars?: Record<string, string> }) {
  const locale = useLocaleListener();
  return <>{t(locale, k, vars)}</>;
}
