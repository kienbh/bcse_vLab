"use client";

import { Cpu, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Device = {
  id: string;
  name: string;
  device_type: string;
  model: string;
  internal_ip: string;
  ssh_port: number;
  status: string;
  capabilities: Record<string, unknown>;
};

const STATUS_CYCLE: Record<string, string> = {
  available: "in_use",
  in_use: "maintenance",
  maintenance: "available",
  offline: "available",
};

function DevicesAdminInner() {
  const { user } = useUser();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
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
    const r = await fetch(`${API}/devices/${d.id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    if (r.ok) refresh();
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <AdminPageHeader
        title="Quản lý thiết bị"
        subtitle={`${devices.length} thiết bị · admin có thể click status để cycle`}
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
        <div className="surface overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-800/50">
              <tr>
                <th className="px-5 py-3 text-left">Name</th>
                <th className="px-5 py-3 text-left">Type</th>
                <th className="px-5 py-3 text-left">Model</th>
                <th className="px-5 py-3 text-left">Internal IP</th>
                <th className="px-5 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {devices.map((d) => (
                <tr key={d.id}>
                  <td className="px-5 py-3 font-mono text-xs">{d.name}</td>
                  <td className="px-5 py-3 font-mono text-xs">{d.device_type}</td>
                  <td className="px-5 py-3">{d.model}</td>
                  <td className="px-5 py-3 font-mono text-xs">{d.internal_ip}:{d.ssh_port}</td>
                  <td className="px-5 py-3">
                    <button
                      type="button"
                      onClick={() => toggleStatus(d)}
                      className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700 hover:bg-vju-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-vju-900/40"
                      title="Click để chuyển status"
                    >
                      {d.status}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
  label, value, onChange, options,
}: { label: string; value: string; onChange: (v: string) => void; options: readonly (readonly [string, string])[] }) {
  return (
    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-vju-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        {options.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
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
