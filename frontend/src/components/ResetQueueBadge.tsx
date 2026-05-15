"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

/**
 * "Đèn sáng" notification badge for the reset request queue. Shown only to
 * admin + lecturer roles. Polls every 30s + subscribes to SSE for realtime
 * updates when a new reset is requested.
 */
export function ResetQueueBadge() {
  const { user } = useUser();
  const [count, setCount] = useState<number>(0);
  const visible = user?.role === "admin" || user?.role === "lecturer";

  const refresh = useCallback(async () => {
    if (!visible) return;
    try {
      const r = await fetch(`${API}/reset-requests/pending/count`, { credentials: "include" });
      if (r.ok) {
        const d = await r.json();
        setCount(typeof d.count === "number" ? d.count : 0);
      }
    } catch {
      /* ignore */
    }
  }, [visible]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [refresh]);

  // SSE realtime — bump on reset.requested/decided
  useEffect(() => {
    if (!visible) return;
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${API}/events/stream`, { withCredentials: true });
      const onChange = () => refresh();
      es.addEventListener("reset.requested", onChange);
      es.addEventListener("reset.queue.updated", onChange);
      es.addEventListener("reset.decided", onChange);
    } catch {
      /* unsupported */
    }
    return () => {
      es?.close();
    };
  }, [visible, refresh]);

  if (!visible) return null;

  return (
    <Link
      href="/admin/reset-queue"
      className="relative inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
      aria-label={`Reset queue (${count} pending)`}
      title={count > 0 ? `${count} yêu cầu reset đang chờ` : "Hàng chờ reset"}
    >
      <Bell className={`h-4 w-4 ${count > 0 ? "text-amber-500" : ""}`} />
      {count > 0 && (
        <>
          <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-bold text-white">
            {count > 99 ? "99+" : count}
          </span>
          <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[16px] animate-ping rounded-full bg-amber-400 opacity-75" />
        </>
      )}
    </Link>
  );
}
