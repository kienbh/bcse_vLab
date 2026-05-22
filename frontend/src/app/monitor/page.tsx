"use client";

import { Activity, Cpu, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const POLL_MS = 15_000;

type Device = { id: string; name: string; device_type: string; model: string; status: string };
type LiveStatus = {
  device_id: string;
  reachable: boolean;
  db_status: string;
  current_booking: {
    user_name: string;
    student_code: string | null;
    start_time: string;
    end_time: string;
  } | null;
  next_booking: { start_time: string; end_time: string } | null;
};

const hm = (iso: string) =>
  new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

function MonitorInner() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [live, setLive] = useState<Record<string, LiveStatus>>({});
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);

  const poll = useCallback(async (ids: string[]) => {
    const results = await Promise.all(
      ids.map((id) =>
        fetch(`${API}/devices/${id}/live-status`, { credentials: "include" })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
      ),
    );
    const map: Record<string, LiveStatus> = {};
    results.forEach((r) => {
      if (r) map[r.device_id] = r;
    });
    setLive(map);
    setUpdatedAt(new Date());
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    fetch(`${API}/devices`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d: Device[]) => {
        // real lab devices first (192.168.2.x reachable ones); keep all
        setDevices(d);
        setLoading(false);
        const ids = d.map((x) => x.id);
        poll(ids);
        timer = setInterval(() => poll(ids), POLL_MS);
      });
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [poll]);

  const inUse = devices.filter((d) => live[d.id]?.current_booking).length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <Activity className="h-7 w-7 text-vju-500" />
            Giám sát thiết bị
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Theo dõi thời gian thực — ai đang dùng thiết bị nào. Tự cập nhật mỗi 15 giây.
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <p className="flex items-center gap-1">
            <RefreshCw className="h-3 w-3" />
            {updatedAt ? `Cập nhật: ${updatedAt.toLocaleTimeString("vi-VN")}` : "Đang tải..."}
          </p>
          <p className="mt-0.5 font-semibold text-vju-600 dark:text-vju-400">
            {inUse}/{devices.length} thiết bị đang được dùng
          </p>
        </div>
      </header>

      {loading ? (
        <div className="surface h-40 animate-pulse" />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {devices.map((d) => {
            const ls = live[d.id];
            const cur = ls?.current_booking;
            const offline = ls && !ls.reachable;
            const maintenance = d.status === "maintenance";
            const state = maintenance
              ? "maintenance"
              : offline
                ? "offline"
                : cur
                  ? "in_use"
                  : "free";
            const ring =
              state === "in_use"
                ? "border-amber-400 bg-amber-50/60 dark:border-amber-700 dark:bg-amber-950/20"
                : state === "free"
                  ? "border-emerald-300 bg-emerald-50/40 dark:border-emerald-800 dark:bg-emerald-950/10"
                  : "border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40";
            return (
              <li key={d.id} className={`rounded-xl border p-4 ${ring}`}>
                <div className="flex items-center justify-between">
                  <p className="font-mono text-xs uppercase text-slate-500">{d.name}</p>
                  <Cpu className="h-4 w-4 text-slate-400" />
                </div>
                <p className="mt-1 text-sm font-semibold">{d.model}</p>
                <div className="mt-3 text-sm">
                  {state === "maintenance" ? (
                    <span className="font-semibold text-slate-500">🔧 Bảo trì</span>
                  ) : state === "offline" ? (
                    <span className="font-semibold text-rose-600 dark:text-rose-400">⚠ Offline</span>
                  ) : state === "in_use" ? (
                    <div>
                      <span className="font-semibold text-amber-700 dark:text-amber-400">
                        ● Đang dùng
                      </span>
                      <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
                        {cur!.user_name}
                        {cur!.student_code ? ` · ${cur!.student_code}` : ""}
                      </p>
                      <p className="text-xs text-slate-500">
                        {hm(cur!.start_time)}–{hm(cur!.end_time)}
                      </p>
                    </div>
                  ) : (
                    <span className="font-semibold text-emerald-700 dark:text-emerald-400">
                      ○ Trống
                    </span>
                  )}
                  {ls?.next_booking && state !== "in_use" && (
                    <p className="mt-1 text-xs text-slate-400">
                      Tiếp theo: {hm(ls.next_booking.start_time)}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function MonitorPage() {
  return (
    <AuthGate>
      <MonitorInner />
    </AuthGate>
  );
}
