"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Cog, Cpu, Database, Gauge, Inbox, Loader2, LogIn, RefreshCw, Rocket, Server, Sparkles, Zap } from "lucide-react";

import { BlockCalendarModal } from "@/components/BlockCalendarModal";
import { BookingModal, SessionLaunchModal, SessionResult } from "@/components/BookingModal";
import { CameraPanel } from "@/components/CameraPanel";
import { Device, DeviceCard, DeviceFamily } from "@/components/DeviceCard";
import { apiGet, useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

const FAMILY_TO_TYPES: Record<DeviceFamily, Device["device_type"][]> = {
  fpga: ["fpga_kv260"],
  jetson: ["jetson_nano", "jetson_orin"],
  rpi: ["rpi4", "rpi5"],
  vps: ["vps"],
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
  vps: {
    title: "VPS — Máy chủ ảo",
    subtitle:
      "Máy ảo Ubuntu trên Proxmox — chạy back-end, server-side, API. Toàn quyền SSH.",
    icon: <Server className="h-6 w-6" />,
    gradient: "from-indigo-500 to-indigo-700",
    cameraLabel: "Khu máy chủ ảo — Node i7 Proxmox",
  },
};

export function FamilyDashboard({ family }: { family: DeviceFamily }) {
  const meta = FAMILY_META[family];
  const { user, loading } = useUser();

  // Public preview when unauth: show family meta + login CTA instead of
  // silently redirecting (so the page doesn't look broken when a guest clicks
  // a feature card on the landing page).
  if (!loading && !user) {
    return <FamilyPreview family={family} meta={meta} />;
  }
  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="surface h-32 animate-pulse" />
      </div>
    );
  }
  // Auth user with must_change_password is still routed by AuthGate via the
  // change-password redirect — wrap children to enforce that.
  if (user!.must_change_password) {
    return <ChangePasswordRedirect family={family} />;
  }
  return <FamilyInner family={family} meta={meta} />;
}

function FamilyPreview({
  family,
  meta,
}: {
  family: DeviceFamily;
  meta: (typeof FAMILY_META)[DeviceFamily];
}) {
  const next = `/devices/${family}`;
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
        <FamilyTabs current={family} />
      </header>

      <div className="surface flex flex-col items-center gap-4 p-12 text-center">
        <div
          className={`grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br ${meta.gradient} text-white shadow-md`}
        >
          <LogIn className="h-6 w-6" />
        </div>
        <div>
          <h2 className="text-xl font-bold">Cần đăng nhập để xem kit</h2>
          <p className="mt-1 max-w-md text-sm text-slate-600 dark:text-slate-400">
            Danh sách thiết bị, trạng thái live, và đặt lịch chỉ hiển thị cho
            sinh viên + giảng viên đã có tài khoản VJU Lab Portal.
          </p>
        </div>
        <Link
          href={`/login?next=${encodeURIComponent(next)}`}
          className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-vju-500 to-vju-700 px-6 py-3 text-sm font-bold text-white shadow-md hover:shadow-lg"
        >
          <LogIn className="h-4 w-4" />
          Đăng nhập
        </Link>
        <p className="text-xs text-slate-400">
          Chưa có tài khoản? Liên hệ giảng viên hoặc admin để được cấp.
        </p>
      </div>
    </div>
  );
}

function ChangePasswordRedirect({ family }: { family: DeviceFamily }) {
  // Re-use AuthGate's pattern: client-side redirect to /change-password.
  if (typeof window !== "undefined") {
    window.location.replace(
      `/change-password?next=${encodeURIComponent(`/devices/${family}`)}`,
    );
  }
  return null;
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
  const [session, setSession] = useState<{
    data: SessionResult;
    bookingId: string;
  } | null>(null);
  // VPS-only: which devices the current user has an ACTIVE long-running grant on.
  // Keyed by device_id, value is the grant valid_to ISO so the card can show "còn N ngày".
  // `null` = not yet loaded → cards render a neutral "checking" state instead of
  // a misleading "request access" CTA when the user actually has a grant.
  const [vpsGrants, setVpsGrants] = useState<Map<string, string> | null>(
    family === "vps" ? null : new Map(),
  );
  // VPS-only: the SV's single currently-held auto block (at most one across
  // ALL VPS — per thầy's spec). Drives "MỞ TERMINAL SSH" / "Huỷ block" /
  // "Bạn đang giữ block trên X" logic on every VPS card. `state` distinguishes
  // a block whose window is open right now ("active" → unlocks SSH) vs one
  // that's scheduled in the future ("upcoming" → shows countdown, no SSH yet).
  type HeldBlock = {
    booking_id: string;
    device_id: string;
    start_time: string;
    end_time: string;
    state: "active" | "upcoming";
  };
  const [heldBlock, setHeldBlock] = useState<HeldBlock | null>(null);
  // Refresh button state — disable + spin while load() is in flight so the
  // user gets immediate feedback the click was registered.
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      // apiGet refreshes the access cookie once on 401 — keeps the dashboard
      // working in a tab that's been open past the 60-min JWT TTL.
      const r = await apiGet(`/devices`);
      if (!r.ok) {
        setError(`HTTP ${r.status}`);
        return;
      }
      const all: Device[] = await r.json();
      const allowed = new Set(FAMILY_TO_TYPES[family]);
      // Sort ascending by name so the "001/002/003 lên đầu" priority that
      // operators expect happens for free — the slug suffix is the kit
      // index, and localeCompare with numeric:true keeps 002 < 010.
      const filtered = all
        .filter((d) => allowed.has(d.device_type))
        .sort((a, b) =>
          a.name.localeCompare(b.name, "en", { numeric: true, sensitivity: "base" }),
        );
      setDevices(filtered);
      setError(null);

      // VPS: pull long-running grants AND the SV's single active auto block
      // in parallel. Both feed into per-card state ("MỞ TERMINAL SSH" if
      // either is active for this VPS, "ĐẶT BLOCK NGAY" otherwise).
      if (family === "vps") {
        const [rg, rb] = await Promise.all([
          apiGet(`/vps-access/grants/mine`),
          apiGet(`/vps-access/blocks/mine`),
        ]);
        if (rg.ok) {
          const all: {
            device_id: string;
            valid_from: string;
            valid_to: string;
            revoked_at: string | null;
          }[] = await rg.json();
          const now = Date.now();
          const active = all.filter(
            (g) =>
              !g.revoked_at &&
              new Date(g.valid_from).getTime() <= now &&
              new Date(g.valid_to).getTime() >= now,
          );
          setVpsGrants(new Map(active.map((g) => [g.device_id, g.valid_to])));
        } else {
          setVpsGrants(new Map());
        }
        if (rb.ok) {
          const blocks: {
            id: string;
            device_id: string;
            start_time: string;
            end_time: string;
          }[] = await rb.json();
          // Backend already filters to scheduled+active and end_time > now,
          // and the spec enforces at most 1 held block per SV — but defend
          // against the API returning more by preferring the earliest one
          // (active, if any; otherwise the soonest upcoming).
          const now = Date.now();
          const sorted = [...blocks].sort(
            (a, b) =>
              new Date(a.start_time).getTime() - new Date(b.start_time).getTime(),
          );
          const active = sorted.find(
            (b) =>
              new Date(b.start_time).getTime() <= now &&
              new Date(b.end_time).getTime() > now,
          );
          const upcoming = active ? null : sorted.find((b) => new Date(b.start_time).getTime() > now);
          const chosen = active ?? upcoming ?? null;
          setHeldBlock(
            chosen
              ? {
                  booking_id: chosen.id,
                  device_id: chosen.device_id,
                  start_time: chosen.start_time,
                  end_time: chosen.end_time,
                  state: active ? "active" : "upcoming",
                }
              : null,
          );
        }
      }
    } catch (e) {
      setError(String(e));
    }
  }, [family]);

  useEffect(() => {
    load();
  }, [load]);

  // Wrapper used by the "Làm mới" button — toggles `refreshing` so the icon
  // spins + the button disables while load() is in flight.
  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load, refreshing]);

  const connect = async (_device: Device, bookingId: string) => {
    // ADR-0013: backend mints a password for this booking and returns the
    // full ssh command. Password is in the response body once.
    const r = await fetch(`${API}/bookings/${bookingId}/access`, {
      method: "POST",
      credentials: "include",
    });
    if (r.ok) {
      const data = (await r.json()) as SessionResult;
      setSession({ data, bookingId });
    } else {
      const e = await r.json().catch(() => ({}));
      const code = e?.detail?.code ?? "ERROR";
      alert(`Không lấy được password: ${code}`);
    }
  };

  // VPS connect — backend auto-creates a booking spanning the SA window and
  // mints the same kind of gateway session, so the SessionLaunchModal works
  // identically to the FPGA/Jetson/Pi flow.
  const connectVps = async (device: Device) => {
    const r = await fetch(`${API}/vps-access/${device.id}/access`, {
      method: "POST",
      credentials: "include",
    });
    if (r.ok) {
      const data = (await r.json()) as SessionResult;
      setSession({ data, bookingId: data.booking_id });
    } else {
      const e = await r.json().catch(() => ({}));
      const code = e?.detail?.code ?? "ERROR";
      const hint = e?.detail?.hint ?? "";
      alert(`Không kết nối được: ${code}${hint ? `\n${hint}` : ""}`);
    }
  };

  // VPS book/cancel — open the visual calendar modal (handles confirm itself).
  const [calendarFor, setCalendarFor] = useState<Device | null>(null);
  const openCalendar = (d: Device) => setCalendarFor(d);

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
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 disabled:opacity-60 disabled:cursor-not-allowed dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Đang tải..." : "Làm mới"}
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
        renderByTier(
          devices,
          family,
          family === "vps" ? openCalendar : setPicked,
          connect,
          family === "vps"
            ? {
                vpsGrants: vpsGrants ?? new Map(),
                grantsLoaded: vpsGrants !== null,
                onVpsConnect: connectVps,
                heldBlock,
                onCancelBlock: openCalendar,
              }
            : undefined,
        )
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
        <SessionLaunchModal
          session={session.data}
          bookingId={session.bookingId}
          onSessionReplaced={(next) =>
            setSession({ data: next, bookingId: session.bookingId })
          }
          onClose={() => setSession(null)}
        />
      )}
      {calendarFor && (
        <BlockCalendarModal
          deviceId={calendarFor.id}
          deviceName={calendarFor.name}
          onClose={() => setCalendarFor(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

// VPS tiers (capabilities.tier) — ordered low → high. Each tier owns a distinct
// visual identity (icon + gradient + panel bg + border) so students can spot
// "máy nào hợp việc của mình" at a glance instead of squinting at chips.
type TierMeta = {
  label: string;
  order: number;
  blurb: string;
  icon: React.ReactNode;
  // Tailwind classes — kept literal (not template-built) so the JIT picks them up.
  headerGradient: string;  // header strip background
  panelBg: string;         // section panel background
  panelBorder: string;     // section panel left-border accent
  badgeBg: string;         // count chip background
};

const TIER_META: Record<string, TierMeta> = {
  thap: {
    label: "VPS tầm thấp",
    order: 1,
    blurb: "2 GB RAM — học tập, dựng web nhẹ, chạy dịch vụ nhỏ",
    icon: <Gauge className="h-6 w-6" />,
    headerGradient: "from-emerald-500 to-teal-600",
    panelBg: "bg-emerald-50/60 dark:bg-emerald-950/20",
    panelBorder: "border-l-emerald-400 dark:border-l-emerald-600",
    badgeBg: "bg-emerald-600 text-white",
  },
  trung: {
    label: "VPS tầm trung",
    order: 2,
    blurb: "4 GB RAM — chạy back-end, API, cơ sở dữ liệu cỡ trung",
    icon: <Database className="h-6 w-6" />,
    headerGradient: "from-sky-500 to-blue-600",
    panelBg: "bg-sky-50/60 dark:bg-sky-950/20",
    panelBorder: "border-l-sky-400 dark:border-l-sky-600",
    badgeBg: "bg-sky-600 text-white",
  },
  cao: {
    label: "VPS tầm cao",
    order: 3,
    blurb: "RAM lớn — tải nặng, nhiều dịch vụ song song",
    icon: <Rocket className="h-6 w-6" />,
    headerGradient: "from-amber-500 to-orange-600",
    panelBg: "bg-amber-50/60 dark:bg-amber-950/20",
    panelBorder: "border-l-amber-400 dark:border-l-amber-600",
    badgeBg: "bg-amber-600 text-white",
  },
  gpu: {
    label: "VPS-GPU",
    order: 4,
    blurb: "Có NVIDIA RTX 6000 Ada (48 GB VRAM) — huấn luyện AI / ML",
    icon: <Zap className="h-6 w-6" />,
    headerGradient: "from-purple-500 via-fuchsia-500 to-purple-700",
    panelBg: "bg-purple-50/60 dark:bg-purple-950/25",
    panelBorder: "border-l-purple-400 dark:border-l-purple-600",
    badgeBg: "bg-purple-600 text-white",
  },
};

const TIER_META_FALLBACK: TierMeta = {
  label: "Khác",
  order: 99,
  blurb: "",
  icon: <Server className="h-6 w-6" />,
  headerGradient: "from-slate-500 to-slate-700",
  panelBg: "bg-slate-50 dark:bg-slate-900/40",
  panelBorder: "border-l-slate-300 dark:border-l-slate-700",
  badgeBg: "bg-slate-600 text-white",
};

/**
 * Render the device grid. VPS carry a `capabilities.tier` tag and are grouped
 * into labelled tier sections (thấp / trung / cao / GPU). FPGA / Jetson / RPi
 * have no tier → one flat grid.
 */
function renderByTier(
  devices: Device[],
  family: DeviceFamily,
  onBook: (d: Device) => void,
  onConnect: (d: Device, bookingId: string) => void,
  vpsExtras?: {
    vpsGrants: Map<string, string>;
    grantsLoaded: boolean;
    onVpsConnect: (d: Device) => void;
    heldBlock: {
      booking_id: string;
      device_id: string;
      start_time: string;
      end_time: string;
      state: "active" | "upcoming";
    } | null;
    onCancelBlock: (d: Device) => void;
  },
): React.ReactNode {
  const held = vpsExtras?.heldBlock ?? null;
  const grid = (list: Device[]) => (
    <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
      {list.map((d) => {
        const isMyHeldBlock = held?.device_id === d.id;
        const isMyActiveBlock = isMyHeldBlock && held?.state === "active";
        const isMyUpcomingBlock = isMyHeldBlock && held?.state === "upcoming";
        return (
          <li key={d.id}>
            <DeviceCard
              device={d}
              family={family}
              onBook={onBook}
              onConnect={onConnect}
              vpsGrantExpiresAt={
                vpsExtras?.vpsGrants.get(d.id) ??
                (isMyActiveBlock ? held?.end_time ?? null : null)
              }
              vpsGrantsLoaded={vpsExtras?.grantsLoaded ?? true}
              onVpsConnect={vpsExtras?.onVpsConnect}
              vpsHasMyActiveBlock={isMyActiveBlock}
              vpsUpcomingBlock={
                isMyUpcomingBlock && held
                  ? { start_time: held.start_time, end_time: held.end_time }
                  : null
              }
              vpsHasOtherHeldBlock={
                held !== null && held.device_id !== d.id
              }
              onCancelMyBlock={vpsExtras?.onCancelBlock}
            />
          </li>
        );
      })}
    </ul>
  );

  const groups = new Map<string, Device[]>();
  for (const d of devices) {
    const t = typeof d.capabilities?.tier === "string" ? (d.capabilities.tier as string) : "";
    const arr = groups.get(t);
    if (arr) arr.push(d);
    else groups.set(t, [d]);
  }
  const keys = [...groups.keys()];
  if (keys.length === 1 && keys[0] === "") return grid(devices);
  keys.sort((a, b) => (TIER_META[a]?.order ?? 99) - (TIER_META[b]?.order ?? 99));

  return (
    <div className="flex flex-col gap-6">
      {keys.map((tk) => {
        const meta = TIER_META[tk] ?? TIER_META_FALLBACK;
        const count = groups.get(tk)!.length;
        return (
          <section
            key={tk || "_none"}
            className={`overflow-hidden rounded-2xl border border-slate-200 ${meta.panelBg} border-l-4 ${meta.panelBorder} shadow-sm dark:border-slate-800`}
          >
            {/* Header strip — gradient + big icon + count, impossible to miss */}
            <div
              className={`flex flex-wrap items-center gap-3 bg-gradient-to-r ${meta.headerGradient} px-5 py-4 text-white shadow-sm`}
            >
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-white/20 backdrop-blur-sm">
                {meta.icon}
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-extrabold tracking-tight md:text-2xl">
                  {meta.label}
                </h2>
                {meta.blurb && (
                  <p className="text-xs font-medium text-white/85 md:text-sm">
                    {meta.blurb}
                  </p>
                )}
              </div>
              <span
                className={`inline-flex shrink-0 items-center gap-1 rounded-full ${meta.badgeBg} px-3 py-1 text-xs font-bold uppercase tracking-wide shadow-md ring-2 ring-white/40`}
              >
                <Sparkles className="h-3 w-3" />
                {count} máy
              </span>
            </div>
            {/* Cards inside the panel — extra padding so they breathe inside the tint */}
            <div className="p-4 md:p-5">{grid(groups.get(tk)!)}</div>
          </section>
        );
      })}
    </div>
  );
}

function FamilyTabs({ current }: { current: DeviceFamily }) {
  const items: { key: DeviceFamily; label: string }[] = [
    { key: "fpga", label: "FPGA" },
    { key: "jetson", label: "Jetson" },
    { key: "rpi", label: "Pi" },
    { key: "vps", label: "VPS" },
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
