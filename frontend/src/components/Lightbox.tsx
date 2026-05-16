"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";

export interface ClickableImageProps {
  src: string;
  alt: string;
  thumbnailClassName?: string;
  /** Optional caption shown over the lightbox bottom */
  caption?: string;
}

/**
 * Image that opens in a full-screen lightbox on click. Esc + backdrop
 * close it. Used on the landing page so visitors can admire the actual
 * lab rack photo at full resolution.
 */
export function ClickableImage({
  src,
  alt,
  thumbnailClassName,
  caption,
}: ClickableImageProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group relative block w-full overflow-hidden text-left"
        aria-label={`Mở ảnh ${alt} ở cỡ đầy đủ`}
      >
        <img
          src={src}
          alt={alt}
          className={`${thumbnailClassName ?? ""} cursor-zoom-in transition-transform group-hover:scale-[1.02]`}
        />
        <span className="pointer-events-none absolute right-3 top-3 rounded-md bg-slate-900/70 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-white opacity-0 backdrop-blur-sm transition group-hover:opacity-100">
          Xem cỡ đầy đủ
        </span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/95 p-4 backdrop-blur-sm animate-fade-in"
          onClick={() => setOpen(false)}
        >
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="absolute right-4 top-4 z-10 grid h-10 w-10 place-items-center rounded-full bg-white/10 text-white shadow-lg hover:bg-white/20"
            aria-label="Đóng"
          >
            <X className="h-5 w-5" />
          </button>
          <img
            src={src}
            alt={alt}
            onClick={(e) => e.stopPropagation()}
            className="max-h-[92vh] max-w-[92vw] cursor-zoom-out rounded-lg object-contain shadow-2xl"
          />
          {caption && (
            <p className="absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full bg-slate-900/70 px-4 py-1.5 text-sm font-medium text-white backdrop-blur-sm">
              {caption}
            </p>
          )}
        </div>
      )}
    </>
  );
}
