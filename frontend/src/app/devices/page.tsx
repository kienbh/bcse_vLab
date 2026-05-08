"use client";

import Link from "next/link";
import { Cpu, Cog, Zap, Filter, Inbox } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { L, useLocaleListener } from "@/components/LocaleText";
import { t } from "@/lib/i18n";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Device = {
  id: string;
  name: string;
  device_type: "fpga_kv260" | "jetson_nano" | "jetson_orin" | "rpi4" | "rpi5";
  model: string;
  status: "available" | "in_use" | "maintenance" | "offline";
  capabilities: Record<string, unknown>;
};

const ICON: Record<Device["device_type"], React.ReactNode> = {
  fpga_kv260: <Cog className="h-5 w-5" />,
  jetson_nano: <Cpu className="h-5 w-5" />,
  jetson_orin: <Cpu className="h-5 w-5" />,
  rpi4: <Zap className="h-5 w-5" />,
  rpi5: <Zap className="h-5 w-5" />,
};

const GRAD: Record<Device["device_type"], string> = {
  fpga_kv260: "from-vju-500 to-vju-700",
  jetson_nano: "from-emerald-500 to-emerald-700",
  jetson_orin: "from-emerald-500 to-emerald-700",
  rpi4: "from-rose-500 to-rose-700",
  rpi5: "from-rose-500 to-rose-700",
};

const STATUS_BADGE: Record<Device["status"], string> = {
  available: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  in_use: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  maintenance: "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  offline: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
};

function familyOf(t: Device["device_type"]): "FPGA" | "Jetson" | "RPi" {
  if (t === "fpga_kv260") return "FPGA";
  if (t === "jetson_nano" || t === "jetson_orin") return "Jetson";
  return "RPi";
}

function DevicesInner() {
  const locale = useLocaleListener();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"ALL" | "FPGA" | "Jetson" | "RPi">("ALL");
  const [status, setStatus] = useState<Device["status"] | "ALL">("ALL");

  useEffect(() => {
    fetch(`${API}/devices`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        setDevices(d);
        setLoading(false);
      });
  }, []);

  const visible = devices.filter(
    (d) => (filter === "ALL" || familyOf(d.device_type) === filter) && (status === "ALL" || d.status === status),
  );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            <L k="page.devices.title" />
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {loading ? "Loading..." : `${visible.length}/${devices.length} thiết bị`}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Filter className="h-4 w-4 text-slate-400" />
          {(["ALL", "FPGA", "Jetson", "RPi"] as const).map((tf) => (
            <button
              key={tf}
              onClick={() => setFilter(tf)}
              className={`rounded-md px-2.5 py-1 font-semibold uppercase tracking-wider transition ${
                filter === tf
                  ? "bg-vju-500 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              {tf}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-slate-300 dark:bg-slate-700" />
          {(["ALL", "available", "in_use", "maintenance"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded-md px-2.5 py-1 font-semibold uppercase tracking-wider transition ${
                status === s
                  ? "bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </header>

      {loading ? (
        <div className="surface h-40 animate-pulse" />
      ) : visible.length === 0 ? (
        <div className="surface flex flex-col items-center justify-center gap-3 p-12 text-center">
          <Inbox className="h-10 w-10 text-slate-300" />
          <h2 className="text-base font-semibold">
            <L k="page.devices.empty.title" />
          </h2>
          <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">
            <L k="page.devices.empty.desc" />
          </p>
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {visible.map((d) => (
            <li key={d.id}>
              <Link
                href={`/devices/${d.id}`}
                className="surface group flex h-full flex-col gap-3 p-5 transition hover:border-vju-300 hover:shadow-md dark:hover:border-vju-700"
              >
                <div className="flex items-start justify-between">
                  <div
                    className={`grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br ${GRAD[d.device_type]} text-white shadow-sm`}
                  >
                    {ICON[d.device_type]}
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_BADGE[d.status]}`}>
                    {t(locale, d.status === "available" ? "status.healthy" : d.status === "in_use" ? "status.starting" : "status.down")}
                  </span>
                </div>
                <div>
                  <p className="font-mono text-xs uppercase tracking-wider text-slate-500">{d.name}</p>
                  <p className="text-base font-semibold">{d.model}</p>
                </div>
                {Object.keys(d.capabilities).length > 0 && (
                  <div className="mt-auto flex flex-wrap gap-1.5">
                    {Object.keys(d.capabilities).slice(0, 4).map((c) => (
                      <span key={c} className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                        {c}
                      </span>
                    ))}
                  </div>
                )}
                <span className="mt-2 inline-block text-xs font-semibold text-vju-500">
                  {d.status === "available" ? "→ Đặt lịch" : "→ Chi tiết"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DevicesPage() {
  return (
    <AuthGate>
      <DevicesInner />
    </AuthGate>
  );
}
