import Link from "next/link";
import Navbar from "@/components/layout/Navbar";
import { PROBLEMS, DIFFICULTY_COLORS, CATEGORY_ICONS } from "@/lib/problems";

const FEATURES = [
  {
    icon: "🎙️",
    title: "Voice-first interaction",
    description:
      "Talk through your design out loud. Alex listens, responds via voice, and pushes back when your answers are weak.",
  },
  {
    icon: "🗂️",
    title: "Interactive whiteboard",
    description:
      "Draw your architecture in real time — drag components, draw connections, and reference your diagram as you explain.",
  },
  {
    icon: "🤖",
    title: "Staff-engineer persona",
    description:
      "Alex is a Senior Staff Engineer. No hints, no hand-holding — just targeted probes on failure modes, trade-offs, and scale.",
  },
  {
    icon: "📊",
    title: "Detailed scorecard",
    description:
      "Every session ends with a structured grade, hire recommendation, strengths, gaps, and a personalised study plan.",
  },
  {
    icon: "⚡",
    title: "Four interview phases",
    description:
      "Intro → Constraints → Design → Deep Dive. The difficulty escalates naturally, just like the real thing.",
  },
  {
    icon: "🎯",
    title: "12 FAANG-grade problems",
    description:
      "URL shortener to distributed K/V store — every problem is calibrated by difficulty and comes with hidden scale targets.",
  },
];

const STATS = [
  { value: "12", label: "System design problems" },
  { value: "4", label: "Difficulty levels" },
  { value: "4", label: "Interview phases" },
  { value: "<500ms", label: "First response latency" },
];

export default function HomePage() {
  const featuredProblems = PROBLEMS.slice(0, 4);

  return (
    <div className="min-h-screen bg-[#0a0a0b]">
      <Navbar />

      {/* Hero */}
      <section className="relative overflow-hidden px-4 pt-20 pb-28 sm:pt-28 sm:pb-36">
        {/* Background glow */}
        <div
          className="pointer-events-none absolute inset-0 -top-40 flex items-start justify-center"
          aria-hidden="true"
        >
          <div className="h-[600px] w-[600px] rounded-full bg-green-500/5 blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-4xl text-center">
          {/* Badge */}
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-green-500/20 bg-green-500/5 px-3 py-1 text-xs font-medium text-green-400">
            <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
            AI-powered system design interview practice
          </div>

          <h1 className="mb-6 text-4xl font-bold tracking-tight text-[#e8e8e8] sm:text-6xl sm:leading-tight">
            Ace your next
            <span className="bg-gradient-to-r from-green-400 to-emerald-500 bg-clip-text text-transparent">
              {" "}system design{" "}
            </span>
            interview
          </h1>

          <p className="mx-auto mb-10 max-w-2xl text-lg text-[#71717a] leading-relaxed">
            Practice with an AI interviewer that thinks like a Staff Engineer.
            Voice-driven, whiteboard-included, no hand-holding — exactly like the real thing.
          </p>

          <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/problems"
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-green-500 px-6 text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
            >
              Browse problems
              <span aria-hidden="true">→</span>
            </Link>
            <Link
              href="/auth/signup"
              className="inline-flex h-11 items-center gap-2 rounded-lg border border-[#27272a] px-6 text-sm font-medium text-[#e8e8e8] hover:border-[#3f3f46] hover:bg-white/5 transition-colors"
            >
              Get started free
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-[#27272a] bg-[#111113]">
        <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
          <dl className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.label} className="text-center">
                <dt className="text-2xl font-bold text-[#e8e8e8] font-mono">{stat.value}</dt>
                <dd className="mt-1 text-sm text-[#71717a]">{stat.label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Featured Problems */}
      <section className="px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold text-[#e8e8e8]">Practice problems</h2>
              <p className="mt-2 text-sm text-[#71717a]">
                12 FAANG-calibrated problems across all difficulty levels
              </p>
            </div>
            <Link
              href="/problems"
              className="text-sm text-green-400 hover:text-green-300 transition-colors hidden sm:block"
            >
              View all →
            </Link>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {featuredProblems.map((problem) => (
              <Link
                key={problem.slug}
                href={`/problems/${problem.slug}`}
                className="group flex flex-col gap-3 rounded-xl border border-[#27272a] bg-[#111113] p-5 hover:border-[#3f3f46] hover:bg-[#18181b] transition-all"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{CATEGORY_ICONS[problem.category]}</span>
                    <span className="text-xs text-[#71717a]">{problem.category}</span>
                  </div>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {problem.difficulty.slice(0, 2).map((d) => (
                      <span
                        key={d}
                        className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLORS[d]}`}
                      >
                        {d}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 className="font-semibold text-[#e8e8e8] group-hover:text-white transition-colors">
                    {problem.title}
                  </h3>
                  <p className="mt-1 text-sm text-[#71717a] line-clamp-2">{problem.brief}</p>
                </div>
                <div className="flex items-center gap-4 text-xs text-[#71717a]">
                  <span>⏱ {problem.estimatedTime}</span>
                  <span>{problem.companies.slice(0, 2).join(" · ")}</span>
                </div>
              </Link>
            ))}
          </div>

          <div className="mt-6 text-center sm:hidden">
            <Link href="/problems" className="text-sm text-green-400 hover:text-green-300">
              View all 12 problems →
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-[#27272a] bg-[#111113] px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <div className="mb-14 text-center">
            <h2 className="text-2xl font-bold text-[#e8e8e8] sm:text-3xl">
              Built like the real interview
            </h2>
            <p className="mt-3 text-[#71717a]">
              Not a quiz app. A full simulation, end to end.
            </p>
          </div>

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => (
              <div
                key={feature.title}
                className="rounded-xl border border-[#27272a] bg-[#0a0a0b] p-6"
              >
                <div className="mb-3 text-2xl">{feature.icon}</div>
                <h3 className="mb-2 font-semibold text-[#e8e8e8]">{feature.title}</h3>
                <p className="text-sm text-[#71717a] leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing preview */}
      <section className="px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-4xl">
          <div className="mb-12 text-center">
            <h2 className="text-2xl font-bold text-[#e8e8e8] sm:text-3xl">Simple pricing</h2>
            <p className="mt-3 text-[#71717a]">Start free. Upgrade when you need more.</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Free tier */}
            <div className="rounded-xl border border-[#27272a] bg-[#111113] p-7">
              <div className="mb-1 text-xs font-medium uppercase tracking-widest text-[#71717a]">
                Free
              </div>
              <div className="mb-6 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-[#e8e8e8]">$0</span>
                <span className="text-[#71717a]">/ month</span>
              </div>
              <ul className="mb-8 space-y-3 text-sm text-[#71717a]">
                {[
                  "3 interviews per month",
                  "Junior & Mid difficulty",
                  "All 12 problems",
                  "AI scorecard",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-2">
                    <span className="text-green-400">✓</span> {item}
                  </li>
                ))}
              </ul>
              <Link
                href="/auth/signup"
                className="block w-full rounded-lg border border-[#27272a] py-2.5 text-center text-sm font-medium text-[#e8e8e8] hover:border-[#3f3f46] hover:bg-white/5 transition-colors"
              >
                Get started
              </Link>
            </div>

            {/* Pro tier */}
            <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-7 relative overflow-hidden">
              <div className="absolute top-0 right-0 m-4">
                <span className="rounded-full bg-green-500 px-2.5 py-0.5 text-xs font-semibold text-[#0a0a0b]">
                  Popular
                </span>
              </div>
              <div className="mb-1 text-xs font-medium uppercase tracking-widest text-green-400">
                Pro
              </div>
              <div className="mb-6 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-[#e8e8e8]">$19</span>
                <span className="text-[#71717a]">/ month</span>
              </div>
              <ul className="mb-8 space-y-3 text-sm text-[#71717a]">
                {[
                  "Unlimited interviews",
                  "All 4 difficulty levels",
                  "All 12 problems",
                  "Full interview history",
                  "Scorecard archive",
                  "Priority AI responses",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-2">
                    <span className="text-green-400">✓</span> {item}
                  </li>
                ))}
              </ul>
              <Link
                href="/pricing"
                className="block w-full rounded-lg bg-green-500 py-2.5 text-center text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
              >
                Start free trial
              </Link>
            </div>
          </div>

          <p className="mt-6 text-center text-sm text-[#71717a]">
            <Link href="/pricing" className="text-green-400 hover:text-green-300">
              See full plan comparison →
            </Link>
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-[#27272a] bg-[#111113] px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-[#e8e8e8] sm:text-4xl">
            Your next interview is in 2 weeks.
          </h2>
          <p className="mt-4 text-[#71717a]">Start practicing today.</p>
          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/problems"
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-green-500 px-8 text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
            >
              Pick a problem
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#27272a] px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <span className="text-sm text-[#71717a]">© 2026 SDI. All rights reserved.</span>
          <div className="flex gap-6 text-sm text-[#71717a]">
            <Link href="/pricing" className="hover:text-[#e8e8e8] transition-colors">Pricing</Link>
            <Link href="/problems" className="hover:text-[#e8e8e8] transition-colors">Problems</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
