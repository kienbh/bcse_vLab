"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type Role = "admin" | "lecturer" | "ta" | "student";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  student_code: string | null;
  is_active: boolean;
  must_change_password: boolean;
}

export interface UserState {
  user: User | null;
  loading: boolean;
  refresh: () => void;
}

let cached: User | null = null;
let inflight: Promise<User | null> | null = null;
const subscribers = new Set<(u: User | null) => void>();

function notify(u: User | null) {
  cached = u;
  subscribers.forEach((cb) => cb(u));
}

async function fetchMe(): Promise<User | null> {
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      let r = await fetch(`${API}/auth/me`, {
        credentials: "include",
        cache: "no-store",
      });
      if (r.status === 401) {
        // Access token expired — try the long-lived refresh cookie once.
        const rf = await fetch(`${API}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        if (rf.ok) {
          r = await fetch(`${API}/auth/me`, { credentials: "include", cache: "no-store" });
        }
      }
      if (!r.ok) return null;
      return (await r.json()) as User;
    } catch {
      return null;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/**
 * POST helper that transparently refreshes an expired access token once and
 * retries — so a long-idle tab doesn't fail an action with NOT_AUTHENTICATED.
 */
export async function apiPost(path: string, body?: unknown): Promise<Response> {
  const opts: RequestInit = {
    method: "POST",
    credentials: "include",
    ...(body !== undefined
      ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {}),
  };
  let r = await fetch(`${API}${path}`, opts);
  if (r.status === 401) {
    const rf = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (rf.ok) r = await fetch(`${API}${path}`, opts);
  }
  return r;
}

export function useUser(): UserState {
  const [user, setUser] = useState<User | null>(cached);
  const [loading, setLoading] = useState<boolean>(cached === null);

  useEffect(() => {
    let alive = true;
    const sub = (u: User | null) => {
      if (alive) setUser(u);
    };
    subscribers.add(sub);
    if (cached !== null) {
      setUser(cached);
      setLoading(false);
    } else {
      fetchMe().then((u) => {
        if (!alive) return;
        notify(u);
        setLoading(false);
      });
    }
    return () => {
      alive = false;
      subscribers.delete(sub);
    };
  }, []);

  return {
    user,
    loading,
    refresh: () => {
      setLoading(true);
      fetchMe().then((u) => {
        notify(u);
        setLoading(false);
      });
    },
  };
}

export function logoutUrl(): string {
  return `${API}/auth/logout`;
}

export async function logout(): Promise<void> {
  try {
    await fetch(logoutUrl(), { method: "POST", credentials: "include" });
  } finally {
    notify(null);
  }
}
