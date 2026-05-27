"use client";

import { Clock, Loader2, Mail, Server, Terminal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { SessionLaunchModal, SessionResult } from "@/components/BookingModal";
import { AuthGate } from "@/components/AuthGate";
import { apiPost, useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const MAX_DAYS = 30;

// Default mailto recipient for long-grant proposals (SV emails their lecturer
// directly — we removed the in-portal request form per thầy's spec
// 2026-05-27). Empty `to` lets the SV pick the right address; we pre-fill
// subject + body so the email writes itself.
const LECTURER_FALLBACK_EMAIL = "";

type Grant = {
  id: string;
  device_id: string;
  valid_from: string;
  valid_to: string;
  reason: string;
  granted_at: string;
  revoked_at: string | null;
  device_name: string | null;
};

function fmt(iso: string) {
  return new Date(iso).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function Inner() {
  const { user } = useUser();
  const router = useRouter();
  const [grants, setGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [session, setSession] = useState<{ data: SessionResult; bookingId: string } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`${API}/vps-access/grants/mine`, { credentials: "include" });
      if (r.ok) setGrants(await r.json());
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Admin/lecturer manage VPS access at /admin/vps-access (pending queue, all
  // grants, direct grant form). The student-facing "my grants" view doesn't
  // fit their workflow — redirect so the nav link works for every role.
  useEffect(() => {
    if (user && (user.role === "admin" || user.role === "lecturer")) {
      router.replace("/admin/vps-access");
    }
  }, [user, router]);

  useEffect(() => {
    if (user && user.role === "student") refresh();
  }, [user, refresh]);

  if (!user) return null;
  if (user.role !== "student") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 text-sm text-slate-500">
        Đang chuyển sang trang quản trị VPS...
      </div>
    );
  }

  const connect = async (grant: Grant) => {
    setConnecting(grant.id);
    setErr(null);
    try {
      const r = await apiPost(`/vps-access/${grant.device_id}/access`);
      if (r.ok) {
        const data = (await r.json()) as SessionResult;
        setSession({ data, bookingId: data.booking_id });
      } else {
        const e = await r.json().catch(() => ({}));
        setErr(`Không kết nối được: ${e?.detail?.code || `HTTP ${r.status}`}`);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setConnecting(null);
    }
  };

  const now = Date.now();
  const activeGrants = grants.filter(
    (g) =>
      !g.revoked_at &&
      new Date(g.valid_from).getTime() <= now &&
      new Date(g.valid_to).getTime() >= now,
  );
  const pastGrants = grants.filter((g) => !activeGrants.includes(g));

  // mailto: builder — pre-fill so SV doesn't have to write the email from
  // scratch. They still type the recipient (their lecturer's email).
  const mailtoSubject = encodeURIComponent(
    `[VJU Lab Portal] Xin proposal quyền VPS dài hạn — ${user.full_name || user.email}`,
  );
  const mailtoBody = encodeURIComponent(
    [
      "Kính gửi thầy/cô,",
      "",
      `Em là ${user.full_name || user.email} (${user.student_code || ""}).`,
      "",
      "Em xin proposal được cấp quyền truy cập VPS dài hạn cho mục đích:",
      "  - Môn / dự án: ",
      "  - VPS cần dùng: (vd sv21, ai01...)",
      "  - Khoảng thời gian xin: từ ngày … đến ngày … (tối đa 30 ngày)",
      "  - Lý do (chạy training nhiều ngày, deploy web, ...): ",
      "",
      "Sau khi thầy/cô duyệt, xin cấp trực tiếp tại:",
      "  https://sv14.bcse-vju.com/admin/vps-access",
      "",
      "Em cảm ơn ạ.",
    ].join("\n"),
  );
  const mailtoHref = `mailto:${LECTURER_FALLBACK_EMAIL}?subject=${mailtoSubject}&body=${mailtoBody}`;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-10 md:px-6">
      <header className="flex items-center gap-3">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 text-white shadow-md">
          <Server className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Quyền VPS của tôi</h1>
          <p className="text-sm text-slate-500">
            Các grant dài hạn đã được giảng viên cấp — kết nối SSH bất cứ lúc nào
            trong thời hạn.
          </p>
        </div>
      </header>

      {err && (
        <div className="surface border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {err}
        </div>
      )}

      {/* CTA — long-grant request flow moved to email (per thầy's spec):
          no in-portal request form; SV emails lecturer who then grants
          directly at /admin/vps-access. */}
      <div className="surface flex flex-col gap-3 border-l-4 border-l-indigo-500 bg-indigo-50/70 p-5 md:flex-row md:items-center md:justify-between dark:bg-indigo-950/30">
        <div className="space-y-1">
          <h2 className="text-base font-bold text-indigo-900 dark:text-indigo-100">
            Cần quyền VPS dài hơn 24h?
          </h2>
          <p className="text-sm text-indigo-800 dark:text-indigo-200">
            Tối đa 24h dùng block-booking tự phục vụ trên trang{" "}
            <a className="underline hover:no-underline" href="/devices/vps">
              /devices/vps
            </a>
            . Nhu cầu dài hơn (tối đa {MAX_DAYS} ngày) → gửi email cho giảng viên
            phụ trách, kèm rõ lý do + khoảng thời gian.
          </p>
        </div>
        <a
          href={mailtoHref}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white shadow-md hover:bg-indigo-700"
        >
          <Mail className="h-4 w-4" />
          Soạn email proposal
        </a>
      </div>

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : (
        <>
          <Section title="Đang có quyền" count={activeGrants.length}>
            {activeGrants.length === 0 ? (
              <Empty msg="Chưa có quyền VPS active dài hạn. Dùng block-booking ở /devices/vps cho nhu cầu ngắn, hoặc gửi email proposal ở trên cho dài hạn." />
            ) : (
              activeGrants.map((g) => (
                <ActiveGrantCard
                  key={g.id}
                  grant={g}
                  busy={connecting === g.id}
                  onConnect={() => connect(g)}
                />
              ))
            )}
          </Section>

          {pastGrants.length > 0 && (
            <Section title="Lịch sử quyền" count={pastGrants.length}>
              {pastGrants.map((g) => (
                <div
                  key={g.id}
                  className="surface flex items-center justify-between p-3 text-sm opacity-70"
                >
                  <div>
                    <p className="font-semibold">{g.device_name}</p>
                    <p className="text-xs text-slate-500">
                      {fmt(g.valid_from)} → {fmt(g.valid_to)}
                      {g.revoked_at && " · Đã thu hồi"}
                    </p>
                  </div>
                </div>
              ))}
            </Section>
          )}
        </>
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
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-baseline gap-2 text-sm font-bold uppercase tracking-wide text-slate-600 dark:text-slate-300">
        {title}
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {count}
        </span>
      </h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function Empty({ msg }: { msg: string }) {
  return (
    <div className="surface p-6 text-center text-sm text-slate-500">{msg}</div>
  );
}

function ActiveGrantCard({
  grant,
  busy,
  onConnect,
}: {
  grant: Grant;
  busy: boolean;
  onConnect: () => void;
}) {
  const daysLeft = Math.max(
    0,
    Math.ceil((new Date(grant.valid_to).getTime() - Date.now()) / 86_400_000),
  );
  return (
    <div className="surface flex items-center justify-between gap-3 p-4">
      <div>
        <p className="font-semibold">
          <Server className="mr-1 inline h-4 w-4 text-indigo-500" />
          {grant.device_name}
        </p>
        <p className="text-xs text-slate-500">
          <Clock className="mr-1 inline h-3 w-3" />
          {fmt(grant.valid_from)} → {fmt(grant.valid_to)} · còn {daysLeft} ngày
        </p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{grant.reason}</p>
      </div>
      <button
        type="button"
        onClick={onConnect}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Terminal className="h-4 w-4" />}
        {busy ? "Đang lấy..." : "Kết nối SSH"}
      </button>
    </div>
  );
}

export default function VpsAccessPage() {
  return (
    <AuthGate>
      <Inner />
    </AuthGate>
  );
}
