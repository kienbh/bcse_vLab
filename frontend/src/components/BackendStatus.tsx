"use client";

import { useEffect, useState } from "react";

type Health = { status: string; service: string; version: string; env: string } | null;

export function BackendStatus() {
  const [health, setHealth] = useState<Health>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const url = process.env.NEXT_PUBLIC_API_URL ?? "/api";
    const tick = async () => {
      try {
        const r = await fetch(`${url}/health`, { cache: "no-store" });
        if (!alive) return;
        if (r.ok) setHealth((await r.json()) as Health);
        else setHealth(null);
      } catch {
        if (alive) setHealth(null);
      } finally {
        if (alive) setLoading(false);
      }
    };
    tick();
    const id = setInterval(tick, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const color = loading
    ? "text-slate-400"
    : health
      ? "text-emerald-500"
      : "text-rose-500";
  const dot = loading ? "bg-slate-400" : health ? "bg-emerald-500" : "bg-rose-500";

  return (
    <div className="surface flex items-center gap-3 px-4 py-3">
      <span className={`relative inline-flex h-2.5 w-2.5 ${dot} rounded-full`}>
        {!loading && health && (
          <span className={`absolute inline-flex h-full w-full ${dot} animate-ping rounded-full opacity-60`} />
        )}
      </span>
      <div className="flex flex-col text-xs">
        <span className={`font-mono ${color}`}>
          {loading ? "checking..." : health ? `${health.service} v${health.version}` : "API offline"}
        </span>
        {health && (
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            env={health.env}
          </span>
        )}
      </div>
    </div>
  );
}
