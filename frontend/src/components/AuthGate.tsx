"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useUser } from "@/lib/auth";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useUser();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      const next = pathname ?? "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    if (user.must_change_password && pathname !== "/change-password") {
      router.replace(`/change-password?next=${encodeURIComponent(pathname ?? "/dashboard")}`);
    }
  }, [user, loading, pathname, router]);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="surface h-32 animate-pulse" />
      </div>
    );
  }
  if (!user) return null;
  if (user.must_change_password && pathname !== "/change-password") return null;
  return <>{children}</>;
}
