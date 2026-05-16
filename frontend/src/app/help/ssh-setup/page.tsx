"use client";

import Link from "next/link";
import { ArrowLeft, KeyRound, Terminal, Network } from "lucide-react";

export default function SshSetupHelpPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-10 md:px-6">
      <header className="flex flex-col gap-3">
        <Link
          href="/bookings"
          className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-vju-700 hover:underline dark:text-vju-200"
        >
          <ArrowLeft className="h-3 w-3" /> Về Bookings
        </Link>
        <h1 className="text-3xl font-bold tracking-tight">
          Hướng dẫn kết nối SSH qua gateway
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Tới giờ slot, bấm <strong>Get SSH access</strong> trong{" "}
          <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">
            /bookings
          </code>{" "}
          → modal hiện 1 password 12 ký tự + lệnh SSH đầy đủ. Copy và dán vào
          terminal hoặc MobaXterm, gõ password đó khi được hỏi — xong, vào
          thẳng kit.
        </p>
      </header>

      {/* OpenSSH CLI */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 text-lg font-bold">
          <Terminal className="h-4 w-4 text-vju-600" /> Cách 1 — Terminal
          (Linux / macOS / Windows PowerShell)
        </h2>
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li>
            Copy lệnh từ modal:{" "}
            <code className="block rounded bg-slate-900 px-3 py-2 font-mono text-xs text-emerald-300">
              ssh -J vlab@ssh.bcse-vju.com:2222 pi@192.168.2.93
            </code>
          </li>
          <li>Dán vào terminal, Enter.</li>
          <li>
            Hỏi password 2 lần:
            <ul className="ml-4 mt-1 list-disc text-xs text-slate-600 dark:text-slate-400">
              <li>
                <strong>Lần 1</strong> (cho{" "}
                <code className="font-mono">vlab@ssh.bcse-vju.com</code>):
                paste password từ modal.
              </li>
              <li>
                <strong>Lần 2</strong> (cho{" "}
                <code className="font-mono">pi@192.168.2.93</code>): password
                kit pi/student do giảng viên cấp. Pilot: hỏi giảng viên hoặc
                để trống nếu kit đã setup pubkey.
              </li>
            </ul>
          </li>
        </ol>
        <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
          <strong>Không có ssh client?</strong> Windows 10+ có sẵn OpenSSH —
          mở PowerShell, gõ luôn. Hoặc cài{" "}
          <a
            href="https://mobaxterm.mobatek.net/download.html"
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            MobaXterm
          </a>{" "}
          (xem cách 2).
        </p>
      </section>

      {/* MobaXterm */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 text-lg font-bold">
          <Network className="h-4 w-4 text-vju-600" /> Cách 2 — MobaXterm
          (Windows GUI)
        </h2>
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li>
            <strong>Session → SSH</strong>
          </li>
          <li>
            <strong>Remote host</strong>: <code className="font-mono">{`<target_host>`}</code>{" "}
            (modal hiện) ·{" "}
            <strong>Username</strong>:{" "}
            <code className="font-mono">{`<target_user>`}</code>
          </li>
          <li>
            <strong>Advanced SSH settings → Network settings</strong> →
            tick <em>Connect through SSH gateway (jump host)</em>
          </li>
          <li>
            Gateway host: <code className="font-mono">ssh.bcse-vju.com</code>{" "}
            · Port: <code className="font-mono">2222</code> · User:{" "}
            <code className="font-mono">vlab</code>
          </li>
          <li>OK → Connect → nhập password modal vào prompt cho vlab.</li>
        </ol>
      </section>

      {/* Lifecycle */}
      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-900/40 dark:bg-emerald-950/30">
        <h2 className="mb-2 flex items-center gap-2 text-lg font-bold text-emerald-900 dark:text-emerald-200">
          <KeyRound className="h-4 w-4" /> Quy tắc lifecycle
        </h2>
        <ul className="ml-5 list-disc space-y-1 text-sm text-emerald-900 dark:text-emerald-200">
          <li>
            Password <strong>cố định trong suốt slot</strong> — mở lại modal
            (bấm <em>Get SSH access</em>) bất cứ lúc nào để xem lại. Cần
            đổi mới? Bấm <em>Regenerate</em>.
          </li>
          <li>
            Password tự hết hạn đúng giờ kết thúc slot. Sau đó: mọi attempt
            đều bị từ chối.
          </li>
          <li>
            Trước 5 phút hết slot, terminal đang chạy sẽ có banner cảnh báo.
            Tới giờ, phiên bị cắt trong ≤30s — lưu file trước.
          </li>
          <li>
            Cần thêm thời gian? Đặt slot mới (nếu chưa hết quota tuần).
          </li>
        </ul>
      </section>

      {/* Troubleshooting */}
      <section className="rounded-xl border border-slate-200 bg-slate-50 p-5 dark:border-slate-700 dark:bg-slate-900/40">
        <h2 className="mb-2 text-lg font-bold">Lỗi thường gặp</h2>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="font-mono text-xs text-rose-600">
              Permission denied (publickey,password)
            </dt>
            <dd className="text-xs text-slate-600 dark:text-slate-400">
              → Password sai hoặc slot chưa bắt đầu / đã hết. Kiểm tra giờ
              trong /bookings, hoặc regenerate password.
            </dd>
          </div>
          <div>
            <dt className="font-mono text-xs text-rose-600">
              channel 0: open failed: administratively prohibited
            </dt>
            <dd className="text-xs text-slate-600 dark:text-slate-400">
              → Bạn đang dùng `-J` tới kit không nằm trong allowlist của slot.
              Đảm bảo target host trong lệnh khớp với kit mà giảng viên cấp.
            </dd>
          </div>
          <div>
            <dt className="font-mono text-xs text-rose-600">
              Connection closed by remote host
            </dt>
            <dd className="text-xs text-slate-600 dark:text-slate-400">
              → Slot có thể vừa hết. Xem giờ trong dashboard, đặt slot mới.
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
