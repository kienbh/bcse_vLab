"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  Copy,
  Check,
  KeyRound,
  Cpu,
  Upload,
  Download,
  Rocket,
  Plug,
  AlertTriangle,
  GitBranch,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Small reusable code block with copy button                          */
/* ------------------------------------------------------------------ */
function CodeBlock({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — ignore, user can still select text */
    }
  };
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-lg bg-slate-900 px-4 py-3 font-mono text-xs leading-relaxed text-emerald-200">
        {children}
      </pre>
      <button
        onClick={onCopy}
        aria-label="Copy"
        className="absolute right-2 top-2 rounded-md bg-slate-700/70 p-1.5 text-slate-200 opacity-0 transition group-hover:opacity-100 hover:bg-slate-600"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-300" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
    </div>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.8em] dark:bg-slate-800">
      {children}
    </code>
  );
}

/* ------------------------------------------------------------------ */
/* Step card — numbered, with icon                                     */
/* ------------------------------------------------------------------ */
function Step({
  n,
  icon,
  title,
  children,
}: {
  n: number;
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="relative rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-3">
        <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-vju-600 text-sm font-bold text-white">
          {n}
        </span>
        <h2 className="flex items-center gap-2 text-lg font-bold">
          {icon}
          {title}
        </h2>
      </div>
      <div className="space-y-3 pl-11 text-sm text-slate-700 dark:text-slate-300">
        {children}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */
export default function GpuGuidePage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-10 md:px-6">
      {/* Header */}
      <header className="flex flex-col gap-3">
        <Link
          href="/bookings"
          className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-vju-700 hover:underline dark:text-vju-200"
        >
          <ArrowLeft className="h-3 w-3" /> Về Bookings
        </Link>
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-vju-500 to-vju-700 text-white shadow">
            <Cpu className="h-6 w-6" />
          </span>
          <h1 className="text-3xl font-bold tracking-tight">
            Hướng dẫn sử dụng GPU
          </h1>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Bạn vừa được cấp một block GPU? Làm theo 4 bước dưới đây:{" "}
          <strong>kết nối → đưa dữ liệu lên → huấn luyện → lấy kết quả về</strong>.
          Không cần biết Linux nâng cao.
        </p>
      </header>

      {/* Prerequisites callout */}
      <div className="rounded-xl border border-vju-200 bg-vju-50 p-5 dark:border-vju-900/40 dark:bg-vju-950/30">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-bold text-vju-900 dark:text-vju-100">
          <KeyRound className="h-4 w-4" /> Trước khi bắt đầu — bạn cần 2 mật khẩu
        </h2>
        <ul className="ml-5 list-disc space-y-1 text-sm text-vju-900 dark:text-vju-100">
          <li>
            <strong>Mật khẩu slot</strong> — bấm{" "}
            <em>Get access</em> trong{" "}
            <Link href="/bookings" className="underline">
              /bookings
            </Link>
            , hiện <strong>đúng 1 lần</strong>.
          </li>
          <li>
            <strong>Mật khẩu user kit</strong> — trong cửa sổ booking, dòng
            &quot;mật khẩu Linux&quot;.
          </li>
        </ul>
        <p className="mt-2 text-xs text-vju-800 dark:text-vju-200">
          🔑 Luôn lấy mật khẩu từ portal, đừng chép của bạn khác — mật khẩu có
          thể được đổi định kỳ.
        </p>
      </div>

      {/* Slot → account table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2 font-semibold">Slot trên portal</th>
              <th className="px-4 py-2 font-semibold">Username khi SSH</th>
              <th className="px-4 py-2 font-semibold">GPU</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {[
              ["ai01", "research01", "GPU 0"],
              ["ai02", "research02", "GPU 1"],
              ["ai03", "research03", "GPU 2"],
            ].map(([slot, user, gpu]) => (
              <tr key={slot} className="bg-white dark:bg-slate-900">
                <td className="px-4 py-2 font-mono">{slot}</td>
                <td className="px-4 py-2 font-mono font-semibold text-vju-700 dark:text-vju-300">
                  {user}
                </td>
                <td className="px-4 py-2">{gpu}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="bg-amber-50 px-4 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          ⚠️ <InlineCode>ai01/02/03</InlineCode> chỉ là tên slot hiển thị — khi
          SSH luôn dùng username tương ứng ở cột giữa (
          <InlineCode>research01</InlineCode> / <InlineCode>research02</InlineCode>{" "}
          / <InlineCode>research03</InlineCode>).
        </p>
      </div>

      {/* Step 1 — connect */}
      <Step n={1} icon={<Plug className="h-4 w-4 text-vju-600" />} title="Kết nối vào máy GPU">
        <p>
          Thêm khối này vào file{" "}
          <InlineCode>~/.ssh/config</InlineCode> (Windows:{" "}
          <InlineCode>C:\Users\&lt;tên&gt;\.ssh\config</InlineCode>) — chỉ làm 1
          lần:
        </p>
        <CodeBlock>{`Host gpu
    HostName 192.168.2.98
    User research01          # đổi theo slot của bạn
    ProxyJump vlab@ssh.bcse-vju.com:2222`}</CodeBlock>
        <p>Sau đó kết nối bằng terminal:</p>
        <CodeBlock>{`ssh gpu`}</CodeBlock>
        <p>
          Sẽ hỏi mật khẩu <strong>2 lần</strong>: (1) mật khẩu slot → (2) mật
          khẩu user kit. Dùng VS Code thì <InlineCode>F1</InlineCode> →{" "}
          <em>Remote-SSH: Connect to Host</em> → chọn <InlineCode>gpu</InlineCode>.
        </p>
        <p>
          Kiểm tra đúng GPU:{" "}
          <InlineCode>nvidia-smi</InlineCode> và{" "}
          <InlineCode>echo $CUDA_VISIBLE_DEVICES</InlineCode>.
        </p>
      </Step>

      {/* Step 2 — upload */}
      <Step n={2} icon={<Upload className="h-4 w-4 text-vju-600" />} title="Đưa dữ liệu LÊN máy GPU">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Chạy trên máy bạn (terminal thường, chưa ssh):
        </p>
        <CodeBlock>{`scp -r ./dataset gpu:~/                 # thư mục
rsync -avP ./dataset/ gpu:~/dataset/    # file lớn / mạng chập chờn`}</CodeBlock>
        <p className="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-800/50">
          <GitBranch className="mt-0.5 h-4 w-4 flex-none text-vju-600" />
          <span>
            <strong>Hoặc git clone thẳng trên máy GPU</strong> (nhanh hơn cho
            code — máy GPU có internet). Sau khi <InlineCode>ssh gpu</InlineCode>:{" "}
            <InlineCode>git clone https://github.com/&lt;user&gt;/&lt;repo&gt;.git</InlineCode>.
            Repo private thì dùng token HTTPS và{" "}
            <strong>đừng lưu token</strong> trên máy dùng chung.
          </span>
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          VS Code Remote: kéo-thả file vào cây thư mục bên trái. Dung lượng:
          quota <strong>300&nbsp;GB</strong> trong <InlineCode>$HOME</InlineCode>.
        </p>
      </Step>

      {/* Step 3 — train */}
      <Step n={3} icon={<Rocket className="h-4 w-4 text-vju-600" />} title="Huấn luyện mô hình">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Chạy trên máy GPU (sau khi ssh):
        </p>
        <CodeBlock>{`python3 -m venv ~/venv && source ~/venv/bin/activate
pip install -r requirements.txt

tmux new -s train          # chạy nền, thoát SSH không làm chết job
python train.py            # Ctrl+B rồi D để tách; quay lại: tmux attach -t train`}</CodeBlock>
        <p>
          Theo dõi GPU: <InlineCode>watch -n 2 nvidia-smi</InlineCode>. Xem
          Jupyter/TensorBoard trên máy mình:{" "}
          <InlineCode>ssh -L 8888:localhost:8888 gpu</InlineCode>.
        </p>
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
          <span>
            <strong>Luôn chạy job trong tmux (hoặc nohup).</strong> Nếu chạy
            trực tiếp, đóng terminal hay mất mạng là job train chết theo.
          </span>
        </p>
      </Step>

      {/* Step 4 — download */}
      <Step n={4} icon={<Download className="h-4 w-4 text-vju-600" />} title="Lấy kết quả VỀ máy bạn">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Chạy trên máy bạn (terminal thường):
        </p>
        <CodeBlock>{`scp -r gpu:~/outputs ./outputs
rsync -avP gpu:~/outputs/ ./outputs/`}</CodeBlock>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          VS Code: chuột phải file/thư mục ở cây bên trái → <strong>Download</strong>.
          Hoặc <InlineCode>git push</InlineCode> ngay trên máy GPU để đẩy kết
          quả lên repo.
        </p>
      </Step>

      {/* Notes */}
      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-900/40 dark:bg-emerald-950/30">
        <h2 className="mb-2 text-sm font-bold text-emerald-900 dark:text-emerald-200">
          Cần nhớ
        </h2>
        <ul className="ml-5 list-disc space-y-1 text-sm text-emerald-900 dark:text-emerald-200">
          <li>
            <strong>Không có quyền sudo</strong> (cố ý). Cần cài package hệ
            thống → nhắn giảng viên. Package Python tự cài trong{" "}
            <InlineCode>venv</InlineCode>.
          </li>
          <li>
            Dữ liệu vẫn còn sau khi hết block, nhưng vẫn tính vào quota 300 GB —
            dọn bằng <InlineCode>rm -rf ~/thu-muc-tam</InlineCode>.
          </li>
          <li>
            Hết block → SSH mới bị từ chối, phiên đang chạy bị cắt (có banner
            cảnh báo trước 5 phút — lưu file kịp).
          </li>
        </ul>
      </section>

      {/* Troubleshooting */}
      <section className="rounded-xl border border-slate-200 bg-slate-50 p-5 dark:border-slate-700 dark:bg-slate-900/40">
        <h2 className="mb-3 text-sm font-bold">Lỗi thường gặp</h2>
        <dl className="space-y-3 text-sm">
          {[
            [
              "Từ chối mật khẩu ở lần hỏi thứ nhất",
              "Sai hoặc hết hạn mật khẩu slot → bấm Get access lấy lại.",
            ],
            [
              "Từ chối ở lần thứ hai dù gõ đúng",
              "Sai username: phải là research01/02/03, không phải ai01/02/03. Kiểm tra dòng User trong ~/.ssh/config.",
            ],
            [
              "administratively prohibited khi scp",
              "Phải dùng gpu:~/... (đã cấu hình ProxyJump), đừng trỏ thẳng vào cổng.",
            ],
            [
              "No space left on device",
              "Hết quota 300 GB → du -sh ~/* để tìm thư mục nặng rồi xóa.",
            ],
            [
              "CUDA out of memory",
              "Giảm batch size, hoặc card đang bị job khác chiếm (xem nvidia-smi).",
            ],
            [
              "Đóng SSH là job train chết",
              "Chưa chạy trong tmux/nohup (xem bước 3).",
            ],
          ].map(([sym, fix]) => (
            <div key={sym}>
              <dt className="font-semibold text-rose-600 dark:text-rose-400">
                {sym}
              </dt>
              <dd className="text-xs text-slate-600 dark:text-slate-400">
                → {fix}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* VPS footnote */}
      <p className="text-center text-xs text-slate-500 dark:text-slate-400">
        Dùng VPS thường (sv21–sv33)? Giống hệt, chỉ đổi{" "}
        <InlineCode>HostName</InlineCode> = IP trong booking và{" "}
        <InlineCode>User = student</InlineCode>.
      </p>
    </div>
  );
}
