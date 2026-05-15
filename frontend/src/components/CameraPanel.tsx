"use client";

import { Camera, CameraOff, Maximize2 } from "lucide-react";
import { useEffect, useState } from "react";

export interface CameraPanelProps {
  label: string;
  /** Optional camera stream URL (RTSP-to-HLS proxied or MJPEG). When null, panel shows placeholder. */
  streamUrl?: string | null;
  /** Storage key — different families remember their own on/off pref */
  storageKey?: string;
}

/**
 * Lab overhead camera placeholder. Toggle on/off to save bandwidth when the
 * stream isn't needed. Persists pref in localStorage. When no stream URL is
 * configured, shows a friendly placeholder so the demo still looks complete.
 */
export function CameraPanel({ label, streamUrl, storageKey = "camera_on" }: CameraPanelProps) {
  const [on, setOn] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const v = localStorage.getItem(storageKey);
    setOn(v === "1");
    setHydrated(true);
  }, [storageKey]);

  const toggle = () => {
    setOn((prev) => {
      const next = !prev;
      localStorage.setItem(storageKey, next ? "1" : "0");
      return next;
    });
  };

  return (
    <section className="surface overflow-hidden p-0">
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-slate-700 to-slate-900 text-white shadow-sm">
            <Camera className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-semibold">{label}</p>
            <p className="text-[11px] text-slate-500">Camera giám sát phòng lab Hòa Lạc</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={toggle}
            disabled={!hydrated}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              on
                ? "bg-emerald-500 text-white hover:bg-emerald-600"
                : "border border-slate-300 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {on ? <Camera className="h-3.5 w-3.5" /> : <CameraOff className="h-3.5 w-3.5" />}
            {on ? "Đang phát" : "Tắt cam"}
          </button>
        </div>
      </header>

      <div className="relative aspect-video bg-slate-900">
        {on ? (
          streamUrl ? (
            <iframe
              src={streamUrl}
              className="h-full w-full"
              title={label}
              allow="autoplay; encrypted-media"
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center text-slate-400">
                <Camera className="mx-auto mb-2 h-8 w-8 opacity-50" />
                <p className="font-mono text-xs">CAMERA_URL chưa được cấu hình</p>
                <p className="mt-1 text-[10px] text-slate-500">
                  Admin cần set <code className="rounded bg-slate-800 px-1 py-0.5">NEXT_PUBLIC_LAB_CAMERA_URL</code>
                </p>
              </div>
            </div>
          )
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-slate-500">
              <CameraOff className="mx-auto mb-2 h-8 w-8 opacity-50" />
              <p className="font-mono text-[11px]">Stream đang tắt — tiết kiệm băng thông</p>
              <button
                type="button"
                onClick={toggle}
                className="mt-3 inline-flex items-center gap-1 rounded-md bg-slate-700 px-3 py-1 text-xs font-semibold text-white hover:bg-slate-600"
              >
                <Camera className="h-3 w-3" />
                Bật xem
              </button>
            </div>
          </div>
        )}
        {on && (
          <span className="pointer-events-none absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-rose-500/90 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-md">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> LIVE
          </span>
        )}
        {streamUrl && (
          <a
            href={streamUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-slate-800/80 px-2 py-1 text-[10px] font-semibold text-white backdrop-blur hover:bg-slate-900"
          >
            <Maximize2 className="h-3 w-3" />
            Toàn màn hình
          </a>
        )}
      </div>
    </section>
  );
}
