import Link from "next/link";
import Navbar from "@/components/layout/Navbar";
import { PROBLEMS, DIFFICULTY_COLORS } from "@/lib/problems";

const MOCK_SESSIONS = [
  {
    id: "s1",
    problemSlug: "url-shortener",
    difficulty: "Senior",
    grade: "B+",
    hire: "Yes",
    completedAt: "2026-05-12T14:30:00Z",
    duration: "43 min",
  },
  {
    id: "s2",
    problemSlug: "rate-limiter",
    difficulty: "Mid",
    grade: "A-",
    hire: "Strong Yes",
    completedAt: "2026-05-10T10:15:00Z",
    duration: "38 min",
  },
  {
    id: "s3",
    problemSlug: "news-feed",
    difficulty: "Staff",
    grade: "C+",
    hire: "Lean No",
    completedAt: "2026-05-08T16:45:00Z",
    duration: "52 min",
  },
];

function gradeColor(grade: string) {
  if (grade.startsWith("A")) return "text-green-400 bg-green-400/10 border-green-400/20";
  if (grade.startsWith("B")) return "text-blue-400 bg-blue-400/10 border-blue-400/20";
  if (grade.startsWith("C")) return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20";
  return "text-red-400 bg-red-400/10 border-red-400/20";
}

function hireColor(hire: string) {
  if (hire === "Strong Yes") return "bg-green-500/10 text-green-400";
  if (hire === "Yes") return "bg-blue-500/10 text-blue-400";
  if (hire === "Lean No") return "bg-yellow-500/10 text-yellow-400";
  return "bg-red-500/10 text-red-400";
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function DashboardPage() {
  const suggested = PROBLEMS.filter(
    (p) => !MOCK_SESSIONS.some((s) => s.problemSlug === p.slug)
  ).slice(0, 3);

  return (
    <div className="min-h-screen bg-[#0a0a0b]">
      <Navbar />

      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[#e8e8e8]">Dashboard</h1>
            <p className="mt-1 text-sm text-[#71717a]">
              3 interviews this month · 2 remaining on free plan
            </p>
          </div>
          <Link
            href="/problems"
            className="inline-flex items-center gap-2 rounded-lg bg-green-500 px-4 py-2 text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
            New interview
          </Link>
        </div>

        {/* Stats strip */}
        <div className="mb-8 grid grid-cols-3 gap-4">
          {[
            { label: "Interviews", value: "3" },
            { label: "Best grade", value: "A-" },
            { label: "Avg duration", value: "44 min" },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-[#27272a] bg-[#111113] p-5 text-center">
              <div className="text-2xl font-bold text-[#e8e8e8] font-mono">{s.value}</div>
              <div className="mt-1 text-xs text-[#71717a]">{s.label}</div>
            </div>
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
          {/* Session history */}
          <div>
            <h2 className="mb-4 text-sm font-semibold text-[#e8e8e8]">Recent interviews</h2>
            <div className="space-y-3">
              {MOCK_SESSIONS.map((session) => {
                const problem = PROBLEMS.find((p) => p.slug === session.problemSlug);
                return (
                  <div
                    key={session.id}
                    className="rounded-xl border border-[#27272a] bg-[#111113] p-5"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <span className="font-medium text-[#e8e8e8] truncate">
                            {problem?.title ?? session.problemSlug}
                          </span>
                          <span
                            className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLORS[session.difficulty as keyof typeof DIFFICULTY_COLORS] ?? ""}`}
                          >
                            {session.difficulty}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-[#71717a]">
                          <span>{formatDate(session.completedAt)}</span>
                          <span>·</span>
                          <span>{session.duration}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span
                          className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border text-sm font-bold font-mono ${gradeColor(session.grade)}`}
                        >
                          {session.grade}
                        </span>
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${hireColor(session.hire)}`}
                        >
                          {session.hire}
                        </span>
                      </div>
                    </div>
                    <div className="mt-4 flex gap-2">
                      <Link
                        href={`/problems/${session.problemSlug}?retake=true`}
                        className="rounded-md border border-[#27272a] px-3 py-1.5 text-xs text-[#71717a] hover:text-[#e8e8e8] hover:border-[#3f3f46] transition-colors"
                      >
                        Retake
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Suggested next */}
          <div>
            <h2 className="mb-4 text-sm font-semibold text-[#e8e8e8]">Try next</h2>
            <div className="space-y-3">
              {suggested.map((problem) => (
                <Link
                  key={problem.slug}
                  href={`/problems/${problem.slug}`}
                  className="group flex items-center gap-3 rounded-xl border border-[#27272a] bg-[#111113] p-4 hover:border-[#3f3f46] hover:bg-[#18181b] transition-all"
                >
                  <span className="text-xl shrink-0">{problem.category === "Storage" ? "🗄️" : problem.category === "Distributed" ? "🌐" : "⚡"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-[#e8e8e8] group-hover:text-white truncate transition-colors">
                      {problem.title}
                    </div>
                    <div className="mt-0.5 text-xs text-[#71717a]">{problem.estimatedTime}</div>
                  </div>
                  <svg className="h-4 w-4 shrink-0 text-[#52525b] group-hover:text-[#71717a]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              ))}
            </div>

            {/* Upgrade nudge */}
            <div className="mt-4 rounded-xl border border-green-500/20 bg-green-500/5 p-4">
              <div className="mb-2 text-xs font-semibold text-green-400">Upgrade to Pro</div>
              <p className="mb-3 text-xs text-[#71717a] leading-relaxed">
                Unlock unlimited interviews, Senior & Staff difficulty, and your full history.
              </p>
              <Link
                href="/pricing"
                className="block w-full rounded-md bg-green-500 py-2 text-center text-xs font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
              >
                See Pro plan
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
