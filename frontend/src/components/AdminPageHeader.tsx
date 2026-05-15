"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

export interface AdminPageHeaderProps {
  /** Page title (shown large) */
  title: string;
  /** Optional subtitle / status line */
  subtitle?: ReactNode;
  /** Optional action buttons on the right */
  actions?: ReactNode;
}

/**
 * Shared header for all `/admin/*` sub-pages. Provides:
 * - Back link to the admin hub (so users don't have to hit the browser Back button)
 * - Title + optional subtitle
 * - Slot on the right for page-specific actions (e.g. "Add device" button)
 */
export function AdminPageHeader({ title, subtitle, actions }: AdminPageHeaderProps) {
  return (
    <div className="flex flex-col gap-3">
      <Link
        href="/admin"
        className="inline-flex w-fit items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-vju-300 hover:bg-vju-50 hover:text-vju-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-vju-700 dark:hover:bg-vju-950/40 dark:hover:text-vju-200"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Quay lại trang Quản trị
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
    </div>
  );
}
