"use client";

import Link from "next/link";
import { Cpu, Users, ListChecks, Activity, ShieldCheck, ClipboardCheck, Settings as SettingsIcon } from "lucide-react";

import { AuthGate } from "@/components/AuthGate";
import { useUser } from "@/lib/auth";

import type { Role } from "@/lib/auth";

type Tile = {
  href: string;
  title: string;
  desc: string;
  icon: React.ReactNode;
  color: string;
  roles: readonly Role[];
};

const TILES: readonly Tile[] = [
  {
    href: "/admin/devices",
    title: "Thiết bị",
    desc: "Thêm/xoá/sửa thiết bị, cấu hình smart-plug, đánh dấu maintenance",
    icon: <Cpu className="h-6 w-6" />,
    color: "from-vju-500 to-vju-700",
    roles: ["admin"],
  },
  {
    href: "/admin/classes",
    title: "Lớp học & sinh viên",
    desc: "Quản lý danh sách sinh viên từng lớp — thêm/xoá sinh viên",
    icon: <ListChecks className="h-6 w-6" />,
    color: "from-emerald-500 to-emerald-700",
    roles: ["admin", "lecturer"],
  },
  {
    href: "/admin/access",
    title: "Quản lý quyền",
    desc: "Gán thiết bị cho lớp, cấp/thu hồi quyền riêng cho sinh viên",
    icon: <ShieldCheck className="h-6 w-6" />,
    color: "from-teal-500 to-teal-700",
    roles: ["admin", "lecturer"],
  },
  {
    href: "/admin/approvals",
    title: "Duyệt đặt lịch",
    desc: "Duyệt / từ chối yêu cầu đặt lịch dùng thiết bị của sinh viên",
    icon: <ClipboardCheck className="h-6 w-6" />,
    color: "from-indigo-500 to-indigo-700",
    roles: ["admin", "lecturer"],
  },
  {
    href: "/admin/sessions",
    title: "Phiên hoạt động",
    desc: "Quan sát + kick session SSH đang chạy",
    icon: <Activity className="h-6 w-6" />,
    color: "from-amber-500 to-amber-700",
    roles: ["admin", "lecturer"],
  },
  {
    href: "/admin/users",
    title: "Người dùng",
    desc: "Tra cứu user, đổi role (admin only), xem quota",
    icon: <Users className="h-6 w-6" />,
    color: "from-rose-500 to-rose-700",
    roles: ["admin"],
  },
  {
    href: "/admin/audit",
    title: "Audit log",
    desc: "Lịch sử mutation + access decision (append-only)",
    icon: <SettingsIcon className="h-6 w-6" />,
    color: "from-slate-500 to-slate-700",
    roles: ["admin"],
  },
];

function AdminInner() {
  const { user } = useUser();
  if (!user) return null;
  const allowed = TILES.filter((t) => t.roles.includes(user.role));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Quản trị</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Bạn đăng nhập với quyền <span className="font-semibold uppercase">{user.role}</span>.
        </p>
      </div>

      {allowed.length === 0 ? (
        <div className="surface p-8 text-center">
          <p className="text-sm text-slate-500">
            Bạn chưa có quyền truy cập trang quản trị. Liên hệ admin nếu cần.
          </p>
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {allowed.map((t) => (
            <li key={t.href}>
              <Link
                href={t.href}
                className="surface group flex h-full flex-col gap-3 p-5 transition hover:border-vju-300 hover:shadow-md dark:hover:border-vju-700"
              >
                <div
                  className={`inline-flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${t.color} text-white shadow-md`}
                >
                  {t.icon}
                </div>
                <h3 className="text-base font-semibold">{t.title}</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400">{t.desc}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AdminPage() {
  return (
    <AuthGate>
      <AdminInner />
    </AuthGate>
  );
}
