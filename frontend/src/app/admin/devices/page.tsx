"use client";

import { Plus, X, Trash2, Power, PowerOff, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type PowerState = "on" | "off" | "resetting";
type Status = "available" | "in_use" | "maintenance" | "offline";

type Device = {
  id: string;
  name: string;
  device_type: string;
  model: string;
  internal_ip: string;
  ssh_port: number;
  status: Status;
  power_state: PowerState;
  power_state_changed_at: string;
  capabilities: Record<string, unknown>;
  notes: string | null;
};

const STATUS_CYCLE: Record<Status, Status> = {
  available: "in_use",
  in_use: "maintenance",
  maintenance: "available",
  offline: "available",
};
const POWER_CYCLE: Record<PowerState, PowerState> = {
  on: "off",
  off: "resetting",
  resetting: "on",
};
const POWER_BADGE: Record<PowerState, { label: string; bg: string; dot: string }> = {
  on:        { label: "Đang bật",   bg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200", dot: "bg-emerald-500" },
  off:       { label: "Đã tắt",     bg: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-200",            dot: "bg-rose-500" },
  resetting: { label: "Đang reset", bg: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200",        dot: "bg-amber-500 animate-pulse" },
};

function DevicesAdminInner() {
  const { user } = useUser();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    device_type: "fpga_kv260",
    model: "",
    internal_ip: "192.168.20.",
    ssh_port: 22,
  });

  const refresh = () => {
    setLoading(true);
    fetch(`${API}/devices`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        setDevices(d);
        setLoading(false);
      });
  };

  useEffect(refresh, []);

  if (!user || user.role !== "admin") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="surface p-6 text-sm">Trang này chỉ dành cho admin.</div>
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await fetch(`${API}/devices`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    if (r.ok) {
      setShowForm(false);
      setForm({ ...form, name: "", model: "" });
      refresh();
    } else {
      const e = await r.json().catch(() => ({}));
      alert(`Tạo thiết bị thất bại: ${JSON.stringify(e)}`);
    }
  };

  const toggleStatus = async (d: Device) => {
    const next = STATUS_CYCLE[d.status] ?? "available";
    setBusyId(d.id);
    const r = await fetch(`${API}/devices/${d.id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    setBusyId(null);
    if (r.ok) refresh();
  };

  const togglePower = async (d: Device) => {
    const next = POWER_CYCLE[d.power_state] ?? "on";
    setBusyId(d.id);
    const r = await fetch(`${API}/admin/devices/${d.id}/power-state`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ power_state: next }),
    });
    setBusyId(null);
    if (r.ok) refresh();
    else alert(`Đổi nguồn thất bại: ${r.status}`);
  };

  const remove = async (d: Device) => {
    if (!confirm(`Xoá thiết bị ${d.name}? Việc này không thể hoàn tác (booking active sẽ chặn xoá).`))
      return;
    setBusyId(d.id);
    const r = await fetch(`${API}/devices/${d.id}`, {
      method: "DELETE",
      credentials: "include",
    });
    setBusyId(null);
    if (r.ok) refresh();
    else {
      const e = await r.json().catch(() => ({}));
      alert(`Xoá thất bại: ${JSON.stringify(e)}`);
    }
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-10 md:px-6">
      <AdminPageHeader
        title="Quản lý thiết bị"
        subtitle={`${devices.length} thiết bị · click status / nguồn để cycle, plug-API chưa online nên admin chỉnh tay`}
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-4 py-2 text-sm font-semibold text-white hover:bg-vju-600"
          >
            {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {showForm ? "Đóng" : "Thêm thiết bị"}
          </button>
        }
      />

      {showForm && (
        <form onSubmit={submit} className="surface grid gap-3 p-5 md:grid-cols-2">
          <Input label="Name (slug)" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <Select
            label="Type"
            value={form.device_type}
            onChange={(v) => setForm({ ...form, device_type: v })}
            options={[
              ["fpga_kv260", "FPGA Kria KV260"],
              ["jetson_nano", "Jetson Nano"],
              ["jetson_orin", "Jetson Orin"],
              ["rpi4", "Raspberry Pi 4"],
              ["rpi5", "Raspberry Pi 5"],
            ]}
          />
          <Input label="Model" value={form.model} onChange={(v) => setForm({ ...form, model: v })} />
          <Input label="Internal IP" value={form.internal_ip} onChange={(v) => setForm({ ...form, internal_ip: v })} />
          <Input
            label="SSH port"
            type="number"
            value={String(form.ssh_port)}
            onChange={(v) => setForm({ ...form, ssh_port: Number(v) })}
          />
          <div className="flex items-end">
            <button
              type="submit"
              className="w-full rounded-md bg-vju-500 px-4 py-2 text-sm font-semibold text-white hover:bg-vju-600"
            >
              Tạo
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="surface h-32 animate-pulse" />
      ) : (
        <div className="surface overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-800/50">
              <tr>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Type</th>
                <th className="px-4 py-3 text-left">Model</th>
                <th className="px-4 py-3 text-left">Internal IP</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Nguồn điện</th>
                <th className="px-4 py-3 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {devices.map((d) => {
                const p = POWER_BADGE[d.power_state];
                const busy = busyId === d.id;
                return (
                  <tr key={d.id} className={busy ? "opacity-50" : ""}>
                    <td className="px-4 py-3 font-mono text-xs">{d.name}</td>
                    <td className="px-4 py-3 font-mono text-xs">{d.device_type}</td>
                    <td className="px-4 py-3">{d.model}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {d.internal_ip}:{d.ssh_port}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => toggleStatus(d)}
                        disabled={busy}
                        className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700 hover:bg-vju-100 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-vju-900/40"
                        title="Click để chuyển status"
                      >
                        {d.status}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => togglePower(d)}
                        disabled={busy}
                        title={`Click để chuyển sang ${POWER_CYCLE[d.power_state]}`}
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold disabled:opacity-50 ${p.bg}`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${p.dot}`} />
                        {p.label}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => remove(d)}
                        disabled={busy}
                        className="inline-flex items-center gap-1 rounded-md border border-rose-300 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40"
                      >
                        {busy ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Trash2 className="h-3 w-3" />
                        )}
                        Xoá
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="surface flex items-center gap-3 p-3 text-[11px] text-slate-500 dark:text-slate-400">
        <Power className="h-3.5 w-3.5 text-emerald-500" /> bật ·
        <PowerOff className="h-3.5 w-3.5 text-rose-500" /> tắt ·
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
          đang reset (admin đợi confirm sau khi cắm/rút plug)
        </span>
      </div>
    </div>
  );
}

function Input({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </label>
  );
}

export default function AdminDevicesPage() {
  return (
    <AuthGate>
      <DevicesAdminInner />
    </AuthGate>
  );
}
