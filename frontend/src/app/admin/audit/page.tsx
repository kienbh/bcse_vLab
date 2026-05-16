"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { ScrollText, RefreshCw, ChevronLeft, ChevronRight, Filter } from "lucide-react";

import { AdminPageHeader } from "@/components/AdminPageHeader";
import { AuthGate } from "@/components/AuthGate";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

type Row = {
  id: number;
  timestamp: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  success: boolean;
};

type ActionTally = { action: string; count: number };

const PAGE_SIZE = 100;

function AuditInner() {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionFilter, setActionFilter] = useState<string>("");
  const [actions, setActions] = useState<ActionTally[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (actionFilter) params.set("action", actionFilter);
      const r = await fetch(`${API}/admin/audit?${params}`, {
        credentials: "include",
      });
      if (!r.ok) throw new Error(`http ${r.status}`);
      const d = await r.json();
      setRows(d.items);
      setTotal(d.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const loadActions = async () => {
    try {
      const r = await fetch(`${API}/admin/audit/actions`, {
        credentials: "include",
      });
      if (r.ok) setActions(await r.json());
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, actionFilter]);

  useEffect(() => {
    loadActions();
  }, []);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const fmt = (iso: string) =>
    new Date(iso).toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

  const actionBadge = useMemo(
    () => (action: string) => {
      // Heuristic color by action prefix
      if (action.startsWith("auth"))
        return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-100";
      if (action.startsWith("booking"))
        return "bg-vju-100 text-vju-700 dark:bg-vju-900/40 dark:text-vju-100";
      if (action.startsWith("session") || action.startsWith("gateway"))
        return "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-100";
      if (action.startsWith("reset"))
        return "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-100";
      return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
    },
    [],
  );

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-8 md:px-6">
      <AdminPageHeader
        title="Audit log"
        subtitle={
          <span className="inline-flex items-center gap-2">
            <ScrollText className="h-3.5 w-3.5" />
            {loading
              ? "Đang tải..."
              : `${total.toLocaleString("vi-VN")} dòng · trang ${page}/${pages}`}
          </span>
        }
        actions={
          <button
            type="button"
            onClick={() => {
              loadActions();
              load();
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        }
      />

      <div className="surface flex flex-wrap items-center gap-2 p-3">
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500">
          <Filter className="h-3.5 w-3.5" />
          Action
        </span>
        <select
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setOffset(0);
          }}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">— Tất cả ({total.toLocaleString("vi-VN")}) —</option>
          {actions.map((a) => (
            <option key={a.action} value={a.action}>
              {a.action} ({a.count})
            </option>
          ))}
        </select>
        {actionFilter && (
          <button
            type="button"
            onClick={() => {
              setActionFilter("");
              setOffset(0);
            }}
            className="text-xs text-vju-600 hover:underline dark:text-vju-300"
          >
            Xoá filter
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
          {error}
        </div>
      )}

      <div className="surface overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50">
            <tr className="font-mono uppercase tracking-wider text-[10px] text-slate-500">
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Target</th>
              <th className="px-3 py-2">IP</th>
              <th className="px-3 py-2">OK</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading && (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-8 text-center text-slate-500"
                >
                  Không có dòng nào khớp filter.
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const open = expandedId === r.id;
              return (
                <Fragment key={r.id}>
                  <tr
                    onClick={() => setExpandedId(open ? null : r.id)}
                    className="cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900/40"
                  >
                    <td className="px-3 py-1.5 font-mono text-[11px] text-slate-600 dark:text-slate-400">
                      {fmt(r.timestamp)}
                    </td>
                    <td className="px-3 py-1.5">
                      {r.actor_email ? (
                        <span className="font-mono text-[11px]">
                          {r.actor_email}
                        </span>
                      ) : (
                        <span className="text-slate-400">system</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5">
                      <span
                        className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${actionBadge(r.action)}`}
                      >
                        {r.action}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 font-mono text-[11px] text-slate-600 dark:text-slate-400">
                      {r.target_type && r.target_id
                        ? `${r.target_type}:${r.target_id.slice(0, 12)}${r.target_id.length > 12 ? "…" : ""}`
                        : "—"}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-[11px] text-slate-500">
                      {r.ip_address ?? "—"}
                    </td>
                    <td className="px-3 py-1.5">
                      <span
                        className={
                          r.success
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-rose-600 dark:text-rose-400"
                        }
                      >
                        {r.success ? "✓" : "✗"}
                      </span>
                    </td>
                  </tr>
                  {open && (
                    <tr className="bg-slate-50 dark:bg-slate-900/40">
                      <td colSpan={6} className="px-3 py-2">
                        <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded bg-slate-900 p-3 font-mono text-[10px] text-emerald-300">
                          {JSON.stringify(r.details, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {rows.length > 0 && (
            <>
              Hiển thị {offset + 1}–{offset + rows.length} / {total.toLocaleString("vi-VN")}
            </>
          )}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Prev
          </button>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            Next
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AuditPage() {
  return (
    <AuthGate>
      <AuditInner />
    </AuthGate>
  );
}
