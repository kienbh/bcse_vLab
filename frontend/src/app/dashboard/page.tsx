"use client";

import Link from "next/link";
import { Calendar, Cpu, Sparkles, Clock, ChevronRight, MessageSquare } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { Countdown } from "@/components/Countdown";
import { L, useLocaleListener } from "@/components/LocaleText";
import { QuotaWidget } from "@/components/QuotaWidget";
import { useUser } from "@/lib/auth";
import { t } from "@/lib/i18n";

type Booking = {
  id: string;
  device_id: string;
  start_time: string;
  end_time: string;
  status: string;
  granted_via: string;
};

type Device = {
  id: string;
  name: string;
  device_type: string;
  model: string;
  status: "available" | "in_use" | "maintenance" | "offline";
};

const STATUS_BADGE: Record<string, string> = {
  available: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  in_use: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  maintenance: "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  offline: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function DashboardInner() {
  const locale = useLocaleListener();
  const { user } = useUser();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);

  useEffect(() => {
    fetch(`${API}/bookings`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setBookings(d.slice(0, 5)));
    fetch(`${API}/devices`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setDevices(d.slice(0, 4)));
  }, []);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          <L k="page.dashboard.title" />
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          <L k="page.dashboard.welcome" /> · <span className="font-semibold">{user?.full_name}</span>
        </p>
      </div>

      <QuotaWidget />

      <div className="grid gap-4 md:grid-cols-3">
        <section className="surface md:col-span-2">
          <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Calendar className="h-4 w-4 text-vju-500" />
              <L k="card.bookings.title" />
            </h2>
            <Link href="/bookings" className="text-xs font-medium text-vju-500 hover:underline">
              <L k="card.bookings.cta" />
            </Link>
          </header>
          {bookings.length === 0 ? (
            <p className="px-5 py-6 text-sm text-slate-500">
              {locale === "vi" ? "Bạn chưa có lịch nào." : "No bookings yet."}
            </p>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {bookings.map((b) => (
                <li key={b.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                  <Clock className="h-4 w-4 text-slate-400" />
                  <div className="flex-1">
                    <p className="font-mono text-xs text-slate-700 dark:text-slate-300">{b.device_id}</p>
                    <p className="text-xs text-slate-500">
                      {new Date(b.start_time).toLocaleString(locale === "vi" ? "vi-VN" : "en-GB")} ·{" "}
                      <span className="italic">via {b.granted_via}</span>
                    </p>
                  </div>
                  <Countdown start={b.start_time} end={b.end_time} compact />
                  <ChevronRight className="h-4 w-4 text-slate-400" />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="surface">
          <header className="border-b border-slate-200 px-5 py-3 dark:border-slate-800">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="h-4 w-4 text-accent-500" />
              <L k="card.actions.title" />
            </h2>
          </header>
          <div className="space-y-2 p-3">
            <Link
              href="/devices"
              className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:border-vju-300 hover:bg-vju-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-vju-700 dark:hover:bg-slate-800"
            >
              <Cpu className="h-4 w-4 text-vju-500" />
              <L k="card.actions.book" />
            </Link>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:border-vju-300 hover:bg-vju-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-vju-700 dark:hover:bg-slate-800"
            >
              <Sparkles className="h-4 w-4 text-accent-500" />
              <L k="card.actions.special" />
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:border-vju-300 hover:bg-vju-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-vju-700 dark:hover:bg-slate-800"
            >
              <MessageSquare className="h-4 w-4 text-emerald-500" />
              <L k="card.actions.contact" />
            </button>
          </div>
        </section>
      </div>

      <section className="surface">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Cpu className="h-4 w-4 text-vju-500" />
            <L k="card.devices.title" />
          </h2>
          <Link href="/devices" className="text-xs font-medium text-vju-500 hover:underline">
            <L k="card.devices.cta" />
          </Link>
        </header>
        {devices.length === 0 ? (
          <p className="px-5 py-6 text-sm text-slate-500">
            {locale === "vi" ? "Chưa có thiết bị." : "No devices."}
          </p>
        ) : (
          <ul className="grid gap-3 p-5 md:grid-cols-2 lg:grid-cols-4">
            {devices.map((d) => (
              <li
                key={d.id}
                className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-vju-300 hover:shadow-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <p className="font-mono text-xs text-slate-500">{d.name}</p>
                <p className="mt-1 text-sm font-semibold">{d.model}</p>
                <span
                  className={`mt-2 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                    STATUS_BADGE[d.status] ?? ""
                  }`}
                >
                  {t(
                    locale,
                    d.status === "available" ? "status.healthy" : d.status === "in_use" ? "status.starting" : "status.down",
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AuthGate>
      <DashboardInner />
    </AuthGate>
  );
}
