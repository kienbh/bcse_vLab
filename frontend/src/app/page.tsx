import Link from "next/link";
import { Cpu, Cog, Zap, Workflow, BookCheck, Terminal, Calendar, ArrowRight } from "lucide-react";

import { BackendStatus } from "@/components/BackendStatus";
import { L } from "@/components/LocaleText";

const FEATURES = [
  {
    titleKey: "feat.fpga.title",
    descKey: "feat.fpga.desc",
    icon: <Cog className="h-6 w-6" />,
    color: "from-vju-500 to-vju-700",
    count: "9 KV260",
    href: "/devices/fpga",
  },
  {
    titleKey: "feat.jetson.title",
    descKey: "feat.jetson.desc",
    icon: <Cpu className="h-6 w-6" />,
    color: "from-emerald-500 to-emerald-700",
    count: "Nano + Orin",
    href: "/devices/jetson",
  },
  {
    titleKey: "feat.rpi.title",
    descKey: "feat.rpi.desc",
    icon: <Zap className="h-6 w-6" />,
    color: "from-rose-500 to-rose-700",
    count: "Pi 4 + Pi 5",
    href: "/devices/rpi",
  },
] as const;

const STEPS = [
  {
    titleKey: "how.step1.title",
    descKey: "how.step1.desc",
    icon: <BookCheck className="h-5 w-5" />,
  },
  {
    titleKey: "how.step2.title",
    descKey: "how.step2.desc",
    icon: <Calendar className="h-5 w-5" />,
  },
  {
    titleKey: "how.step3.title",
    descKey: "how.step3.desc",
    icon: <Terminal className="h-5 w-5" />,
  },
] as const;

export default function HomePage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-16 px-4 py-12 md:px-6 md:py-16">
      <section className="grid items-center gap-10 md:grid-cols-[1.1fr_1fr]">
        <div className="animate-fade-in space-y-6">
          <p className="inline-flex items-center gap-2 rounded-full border border-vju-100 bg-vju-50 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-vju-700 dark:border-vju-900/40 dark:bg-vju-900/20 dark:text-vju-100">
            <span className="h-1.5 w-1.5 rounded-full bg-vju-500" />
            <L k="hero.eyebrow" />
          </p>
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-slate-900 md:text-5xl lg:text-6xl dark:text-white">
            <L k="hero.title" />
          </h1>
          <p className="max-w-prose text-base leading-relaxed text-slate-600 md:text-lg dark:text-slate-300">
            <L k="hero.subtitle" />
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-lg bg-vju-500 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:bg-vju-600 hover:shadow-lg"
            >
              <L k="hero.cta.login" />
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/devices"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white/60 px-5 py-3 text-sm font-semibold text-slate-800 backdrop-blur transition hover:bg-white dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <Cpu className="h-4 w-4" />
              <L k="hero.cta.devices" />
            </Link>
          </div>
          <div className="pt-4">
            <BackendStatus />
          </div>
        </div>

        <div className="relative hidden md:block">
          <div className="absolute inset-0 -z-10 rounded-3xl bg-gradient-to-br from-vju-500/10 via-transparent to-accent-500/10 blur-3xl" />
          <div className="surface relative grid grid-cols-2 gap-3 p-4">
            {FEATURES.slice(0, 4).map((f, i) => (
              <div
                key={i}
                className={`relative overflow-hidden rounded-xl bg-gradient-to-br ${f.color} p-4 text-white shadow-md`}
              >
                <div className="flex items-center justify-between">
                  {f.icon}
                  <span className="rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-mono uppercase">
                    {f.count}
                  </span>
                </div>
                <p className="mt-3 text-sm font-semibold leading-snug">
                  <L k={f.titleKey} />
                </p>
              </div>
            ))}
            <div className="col-span-2 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Workflow className="h-4 w-4" /> ARCHITECTURE
              </div>
              <p className="mt-1 font-mono text-xs text-slate-700 dark:text-slate-300">
                Cloudflare → SV08 nginx → SV14 Docker stack → Hòa Lạc lab pool
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-6 animate-slide-up">
        <h2 className="text-2xl font-bold tracking-tight md:text-3xl">
          <L k="how.title" />
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <div key={i} className="surface relative space-y-3 p-6">
              <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-vju-50 text-vju-700 dark:bg-vju-900/30 dark:text-vju-100">
                {s.icon}
              </div>
              <h3 className="text-base font-semibold">
                <L k={s.titleKey} />
              </h3>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                <L k={s.descKey} />
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-6 animate-slide-up">
        <div className="grid gap-4 md:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Link
              key={i}
              href={f.href}
              className="surface group relative space-y-3 overflow-hidden p-6 transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div
                className={`inline-flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${f.color} text-white shadow-md`}
              >
                {f.icon}
              </div>
              <h3 className="text-lg font-semibold">
                <L k={f.titleKey} />
              </h3>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                <L k={f.descKey} />
              </p>
              <div className="flex items-center justify-between pt-1">
                <span className="font-mono text-[11px] uppercase tracking-wider text-slate-400">
                  {f.count}
                </span>
                <span className="text-xs font-semibold text-vju-500 transition group-hover:translate-x-0.5">
                  Mở dashboard →
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
