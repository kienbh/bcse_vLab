"use client";

import { Camera, CameraOff, Maximize2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

export interface CameraPanelProps {
  label: string;
  /** Optional camera stream URL (RTSP-to-HLS proxied or MJPEG). When null, panel shows placeholder. */
  streamUrl?: string | null;
  /** Storage key — different families remember their own on/off pref */
  storageKey?: string;
}

/**
 * Lab overhead camera panel. Compact by default (slim strip on the device
 * page) — students can hit "Mở rộng" to pop a full-size preview without
 * leaving the page. Toggle on/off persists in localStorage to save bandwidth.
 */
export function CameraPanel({ label, streamUrl, storageKey = "camera_on" }: CameraPanelProps) {
  const [on, setOn] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [zoom, setZoom] = useState(false);

  useEffect(() => {
    const v = localStorage.getItem(storageKey);
    setOn(v === "1");
    setHydrated(true);
  }, [storageKey]);

  const toggle = useCallback(() => {
    setOn((prev) => {
      const next = !prev;
      localStorage.setItem(storageKey, next ? "1" : "0");
      return next;
    });
  }, [storageKey]);

  // ESC closes the zoom modal
  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoom(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom]);

  const placeholder = (
    <div className="flex h-full items-center justify-center text-center">
      <div className="text-slate-400">
        <Camera className="mx-auto mb-1 h-6 w-6 opacity-50" />
        <p className="font-mono text-[10px]">CAMERA_URL chưa được cấu hình</p>
      </div>
    </div>
  );

  const streamFrame = streamUrl ? (
    <iframe
      src={streamUrl}
      className="h-full w-full"
      title={label}
      allow="autoplay; encrypted-media"
    />
  ) : (
    placeholder
  );

  return (
    <>
      <section className="surface flex items-center gap-3 overflow-hidden p-2 pl-3">
        {/* Compact thumbnail — fixed-width 16:9 strip, much smaller than before */}
        <div className="relative h-20 w-36 shrink-0 overflow-hidden rounded-md bg-slate-900 md:h-24 md:w-44">
          {on ? (
            streamFrame
          ) : (
            <div className="flex h-full items-center justify-center text-slate-500">
              <CameraOff className="h-6 w-6 opacity-50" />
            </div>
          )}
          {on && (
            <span className="pointer-events-none absolute right-1 top-1 inline-flex items-center gap-1 rounded-full bg-rose-500/90 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white shadow-md">
              <span className="h-1 w-1 animate-pulse rounded-full bg-white" /> LIVE
            </span>
          )}
        </div>

        {/* Right-side meta + controls */}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-slate-700 to-slate-900 text-white shadow-sm">
            <Camera className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{label}</p>
            <p className="truncate text-[11px] text-slate-500">
              {on ? "Đang phát · ấn Mở rộng để xem to" : "Tắt cam để tiết kiệm băng thông"}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={toggle}
              disabled={!hydrated}
              className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold transition ${
                on
                  ? "bg-emerald-500 text-white hover:bg-emerald-600"
                  : "border border-slate-300 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
              title={on ? "Tắt camera" : "Bật camera"}
            >
              {on ? <Camera className="h-3.5 w-3.5" /> : <CameraOff className="h-3.5 w-3.5" />}
              <span className="hidden md:inline">{on ? "Đang phát" : "Bật cam"}</span>
            </button>
            <button
              type="button"
              onClick={() => setZoom(true)}
              disabled={!on}
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              title={on ? "Phóng to xem chi tiết" : "Bật cam trước rồi mới mở rộng được"}
            >
              <Maximize2 className="h-3.5 w-3.5" />
              <span className="hidden md:inline">Mở rộng</span>
            </button>
          </div>
        </div>
      </section>

      {/* Zoom modal — backdrop click + ESC + close button all close */}
      {zoom && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          onClick={() => setZoom(false)}
        >
          <div
            className="relative w-full max-w-5xl overflow-hidden rounded-xl bg-slate-950 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2 text-white">
              <div className="flex items-center gap-2">
                <Camera className="h-4 w-4 text-rose-400" />
                <span className="text-sm font-semibold">{label}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/90 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> LIVE
                </span>
              </div>
              <div className="flex items-center gap-2">
                {streamUrl && (
                  <a
                    href={streamUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-xs font-semibold text-white hover:bg-slate-700"
                  >
                    <Maximize2 className="h-3 w-3" />
                    Tab mới
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setZoom(false)}
                  className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-xs font-semibold text-white hover:bg-slate-700"
                  title="Đóng (ESC)"
                >
                  <X className="h-3.5 w-3.5" />
                  Đóng
                </button>
              </div>
            </div>
            <div className="aspect-video bg-slate-900">{streamFrame}</div>
          </div>
        </div>
      )}
    </>
  );
}
