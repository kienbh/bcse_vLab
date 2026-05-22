"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Cog, Cpu, Inbox, Loader2, RefreshCw, Zap } from "lucide-react";

import { AuthGate } from "@/components/AuthGate";
import { BookingModal, SessionLaunchModal, SessionResult } from "@/components/BookingModal";
import { CameraPanel } from "@/components/CameraPanel";
import { Device, DeviceCard, DeviceFamily } from "@/components/DeviceCard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

const FAMILY_TO_TYPES: Record<DeviceFamily, Device["device_type"][]> = {
  fpga: ["fpga_kv260"],
  jetson: ["jetson_nano", "jetson_orin"],
  rpi: ["rpi4", "rpi5"],
};

const FAMILY_META: Record<DeviceFamily, {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  gradient: string;
  cameraLabel: string;
}> = {
  fpga: {
    title: "FPGA — AMD Kria",
    subtitle: "Zynq UltraScale+ MPSoC. PetaLinux / Ubuntu on-board, nạp bitstream qua xmutil.",
    icon: <Cog className="h-6 w-6" />,
    gradient: "from-vju-500 to-vju-700",
    cameraLabel: "Khu FPGA — Lab Hòa Lạc",
  },
  jetson: {
    title: "NVIDIA Jetson",
    subtitle: "GPU edge — JetPack Linux, CUDA / TensorRT cho inference.",
    icon: <Cpu className="h-6 w-6" />,
    gradient: "from-emerald-500 to-teal-700",
    cameraLabel: "Khu Jetson — Lab Hòa Lạc",
  },
  rpi: {
    title: "Raspberry Pi",
    subtitle: "Linux đa năng + GPIO — thử nghiệm sensor, IoT, embedded protocols.",
    icon: <Zap className="h-6 w-6" />,
    gradient: "from-rose-500 to-pink-700",
    cameraLabel: "Khu Raspberry Pi — Lab Hòa Lạc",
  },
};

export function FamilyDashboard({ family }: { family: DeviceFamily }) {
  const meta = FAMILY_META[family];
  return (
    <AuthGate>
      <FamilyInner family={family} meta={meta} />
    </AuthGate>
  );
}

function FamilyInner({
  family,
  meta,
}: {
  family: DeviceFamily;
  meta: (typeof FAMILY_META)[DeviceFamily];
}) {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Device | null>(null);
  const [session, setSession] = useState<SessionResult | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/devices`, { credentials: "include" });
      if (!r.ok) {
        setError(`HTTP ${r.status}`);
        return;
      }
      const all: Device[] = await r.json();
      const allowed = new Set(FAMILY_TO_TYPES[family]);
      setDevices(all.filter((d) => allowed.has(d.device_type)));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [family]);

  useEffect(() => {
    load();
  }, [load]);

  const connect = async (device: Device, bookingId: string) => {
    const r = await fetch(`${API}/sessions/provision/${bookingId}`, {
      method: "POST",
      credentials: "include",
    });
    if (r.ok) {
      setSession((await r.json()) as SessionResult);
      return;
    }
    const e = await r.json().catch(() => ({}));
    const code = e?.detail?.code ?? "ERROR";
    if (code === "SESSION_EXISTS") {
      // Already provisioned — re-open the existing web terminal instead of erroring.
      const r2 = await fetch(`${API}/sessions/by-booking/${bookingId}`, {
        credentials: "include",
      });
      if (r2.ok) {
        setSession((await r2.json()) as SessionResult);
        return;
      }
    }
    alert(`Không mở được session: ${code}`);
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-4">
          <div
            className={`grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br ${meta.gradient} text-white shadow-md`}
          >
            {meta.icon}
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{meta.title}</h1>
            <p className="max-w-xl text-sm text-slate-600 dark:text-slate-400">
              {meta.subtitle}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <FamilyTabs current={family} />
          <button
            type="button"
            onClick={load}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Làm mới
          </button>
        </div>
      </header>

      <CameraPanel
        label={meta.cameraLabel}
        streamUrl={process.env.NEXT_PUBLIC_LAB_CAMERA_URL ?? null}
        storageKey={`camera_on_${family}`}
      />

      {error && (
        <div className="surface border-rose-300 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          Không tải được danh sách: {error}
        </div>
      )}

      {devices === null ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Đang tải thiết bị...
        </div>
      ) : devices.length === 0 ? (
        <div className="surface flex flex-col items-center justify-center gap-3 p-12 text-center">
          <Inbox className="h-10 w-10 text-slate-300" />
          <h2 className="text-base font-semibold">Chưa có kit nào trong nhóm này</h2>
          <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">
            Admin chưa thêm thiết bị, hoặc kit chưa được seed. Xem trang
            <Link href="/admin/devices" className="ml-1 font-semibold text-vju-500 hover:underline">
              Quản trị / Thiết bị
            </Link>
            .
          </p>
        </div>
      ) : (
        <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {devices.map((d) => (
            <li key={d.id}>
              <DeviceCard
                device={d}
                family={family}
                onBook={setPicked}
                onConnect={connect}
              />
            </li>
          ))}
        </ul>
      )}

      {picked && (
        <BookingModal
          device={picked}
          onClose={() => setPicked(null)}
          onBooked={() => {
            setPicked(null);
            load();
          }}
        />
      )}
      {session && (
        <SessionLaunchModal session={session} onClose={() => setSession(null)} />
      )}
    </div>
  );
}

function FamilyTabs({ current }: { current: DeviceFamily }) {
  const items: { key: DeviceFamily; label: string }[] = [
    { key: "fpga", label: "FPGA" },
    { key: "jetson", label: "Jetson" },
    { key: "rpi", label: "Pi" },
  ];
  return (
    <div className="inline-flex rounded-md border border-slate-300 bg-white text-xs dark:border-slate-700 dark:bg-slate-900">
      {items.map((it) => (
        <Link
          key={it.key}
          href={`/devices/${it.key}`}
          className={`px-3 py-1.5 font-semibold transition ${
            current === it.key
              ? "bg-vju-500 text-white"
              : "text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800"
          }`}
        >
          {it.label}
        </Link>
      ))}
    </div>
  );
}
