"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Calendar, Cpu, Loader2, Sparkles, Clock } from "lucide-react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Device = {
  id: string;
  name: string;
  device_type: string;
  model: string;
  status: string;
  capabilities: Record<string, unknown>;
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function defaultStartIso(): string {
  // Default to next round hour
  const d = new Date();
  d.setHours(d.getHours() + 1, 0, 0, 0);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function plusHoursIso(localIso: string, hours: number): string {
  const d = new Date(localIso);
  d.setHours(d.getHours() + hours);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type Suggestion = { start: string; end: string };

function isoToLocalInput(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function DeviceDetailInner() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const router = useRouter();
  const [device, setDevice] = useState<Device | null>(null);
  const [loading, setLoading] = useState(true);
  const [start, setStart] = useState(defaultStartIso());
  const [end, setEnd] = useState(plusHoursIso(defaultStartIso(), 2));
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loadingSuggest, setLoadingSuggest] = useState(false);

  const durationHours = useMemo(() => {
    try {
      const s = new Date(start).getTime();
      const e = new Date(end).getTime();
      const h = (e - s) / 3600_000;
      return h > 0 && h <= 8 ? h : 2;
    } catch {
      return 2;
    }
  }, [start, end]);

  const loadSuggestions = async () => {
    if (!id) return;
    setLoadingSuggest(true);
    const r = await fetch(
      `${API}/devices/${id}/suggest-slots?duration_hours=${durationHours}&days=7&count=5`,
      { credentials: "include" },
    );
    if (r.ok) {
      const d = await r.json();
      setSuggestions(d.suggestions ?? []);
    }
    setLoadingSuggest(false);
  };

  useEffect(() => {
    if (!id) return;
    fetch(`${API}/devices/${id}`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        setDevice(d);
        setLoading(false);
      });
  }, [id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!device) return;
    setSubmitting(true);
    setResult(null);
    try {
      const r = await fetch(`${API}/bookings`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: device.id,
          start_time: new Date(start).toISOString(),
          end_time: new Date(end).toISOString(),
          notes: notes || null,
        }),
      });
      if (r.ok) {
        setResult({ ok: true, msg: "Đặt lịch thành công." });
        setTimeout(() => router.push("/bookings"), 1200);
      } else {
        const err = await r.json().catch(() => ({}));
        const code = err?.detail?.code ?? "ERROR";
        const details = err?.detail?.details ? ` (${JSON.stringify(err.detail.details)})` : "";
        setResult({ ok: false, msg: `${code}${details}` });
        // On conflict, auto-load suggestions
        if (code === "BOOKING_CONFLICT") loadSuggestions();
      }
    } catch (e) {
      setResult({ ok: false, msg: String(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const applySuggestion = (s: Suggestion) => {
    setStart(isoToLocalInput(s.start));
    setEnd(isoToLocalInput(s.end));
    setResult(null);
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <div className="surface h-32 animate-pulse" />
      </div>
    );
  }
  if (!device) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 text-center">
        <p className="text-sm text-slate-500">Không tìm thấy thiết bị.</p>
        <Link href="/devices" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-vju-500 hover:underline">
          <ArrowLeft className="h-4 w-4" /> Trở lại danh sách
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-10 md:px-6">
      <Link href="/devices" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200">
        <ArrowLeft className="h-4 w-4" /> Danh sách thiết bị
      </Link>

      <header className="flex items-start gap-4">
        <div className="grid h-14 w-14 place-items-center rounded-xl bg-gradient-to-br from-vju-500 to-vju-700 text-white shadow-md">
          <Cpu className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{device.model}</h1>
          <p className="font-mono text-xs uppercase text-slate-500">
            {device.name} · {device.device_type} · {device.status}
          </p>
          {Object.keys(device.capabilities).length > 0 && (
            <p className="mt-1 text-xs text-slate-500">
              Capabilities: {Object.keys(device.capabilities).join(", ")}
            </p>
          )}
        </div>
      </header>

      <form onSubmit={submit} className="surface flex flex-col gap-4 p-6">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Calendar className="h-4 w-4 text-vju-500" />
          Đặt lịch sử dụng
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
            Bắt đầu
            <input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              required
            />
          </label>
          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
            Kết thúc
            <input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              required
            />
          </label>
        </div>
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Ghi chú (optional)
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            maxLength={500}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            placeholder="VD: Lab 2 — synthesise bitstream cho thí nghiệm 3"
          />
        </label>

        <button
          type="submit"
          disabled={submitting || device.status !== "available"}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-vju-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-vju-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calendar className="h-4 w-4" />}
          {device.status !== "available"
            ? `Thiết bị ${device.status} — không đặt được`
            : "Đặt lịch"}
        </button>

        {result && (
          <div
            className={`rounded-md border p-3 text-xs ${
              result.ok
                ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200"
                : "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200"
            }`}
          >
            {result.msg}
          </div>
        )}

        <p className="text-xs text-slate-500">
          ⓘ Slot trong cửa sổ thời gian giảng viên cấp + dưới 8 giờ + không vượt quota tuần.
        </p>
      </form>

      <section className="surface flex flex-col gap-3 p-5">
        <header className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="h-4 w-4 text-accent-500" />
            Slot trống gần nhất ({durationHours.toFixed(1)}h)
          </h2>
          <button
            type="button"
            onClick={loadSuggestions}
            disabled={loadingSuggest}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            {loadingSuggest ? "..." : "Tải"}
          </button>
        </header>
        {suggestions.length === 0 ? (
          <p className="text-xs text-slate-500">
            Click &ldquo;Tải&rdquo; để xem 5 slot trống gần nhất với độ dài bằng slot đang chọn.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {suggestions.map((s, i) => {
              const sd = new Date(s.start);
              const ed = new Date(s.end);
              return (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => applySuggestion(s)}
                    className="flex w-full items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-xs hover:border-vju-300 hover:bg-vju-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-vju-700 dark:hover:bg-slate-800"
                  >
                    <span className="flex items-center gap-2">
                      <Clock className="h-3 w-3 text-slate-400" />
                      <span className="font-mono font-semibold">
                        {sd.toLocaleString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="text-slate-400">→</span>
                      <span className="font-mono">
                        {ed.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </span>
                    <span className="rounded bg-vju-100 px-2 py-0.5 text-[10px] font-bold uppercase text-vju-700 dark:bg-vju-900/40 dark:text-vju-100">
                      Chọn
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

export default function DeviceDetailPage() {
  return (
    <AuthGate>
      <DeviceDetailInner />
    </AuthGate>
  );
}
