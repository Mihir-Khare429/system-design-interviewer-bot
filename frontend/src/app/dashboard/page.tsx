"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Navbar from "@/components/layout/Navbar";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { DIFFICULTY_COLORS } from "@/lib/problems";

type InterviewRow = {
  id: number;
  session_id: string;
  problem_slug: string | null;
  difficulty: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  estimated_cost_usd: number;
  scorecard: Record<string, unknown> | null;
};

type InterviewsResponse = {
  items: InterviewRow[];
  count: number;
  quota: { plan: string; used: number; limit: number; remaining: number };
};

function gradeColor(grade: string) {
  if (grade.startsWith("A")) return "text-green-400 bg-green-400/10 border-green-400/20";
  if (grade.startsWith("B")) return "text-blue-400 bg-blue-400/10 border-blue-400/20";
  if (grade.startsWith("C")) return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20";
  return "text-red-400 bg-red-400/10 border-red-400/20";
}

function hireColor(hire: string) {
  if (hire.includes("Strong Yes")) return "bg-green-500/10 text-green-400";
  if (hire.includes("Yes")) return "bg-blue-500/10 text-blue-400";
  if (hire.includes("Lean No")) return "bg-yellow-500/10 text-yellow-400";
  return "bg-red-500/10 text-red-400";
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function durationMin(start: string | null, end: string | null) {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return `${Math.max(1, Math.round(ms / 60000))} min`;
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<InterviewsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push("/auth/signin");
      return;
    }
    api<InterviewsResponse>("/api/interviews")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"));
  }, [authLoading, user, router]);

  if (authLoading || !data) {
    return (
      <div className="min-h-screen bg-[#0a0a0b]">
        <Navbar />
        <div className="mx-auto max-w-5xl px-4 py-10 text-sm text-[#71717a]">
          {error ?? "Loading…"}
        </div>
      </div>
    );
  }

  const grades = data.items
    .map((r) => (r.scorecard?.grade as string | undefined) ?? "")
    .filter(Boolean);
  const bestGrade = grades.sort()[0] ?? "—";
  const totalSpent = data.items.reduce((sum, r) => sum + (r.estimated_cost_usd || 0), 0);

  return (
    <div className="min-h-screen bg-[#0a0a0b]">
      <Navbar />

      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[#e8e8e8]">Dashboard</h1>
            <p className="mt-1 text-sm text-[#71717a]">
              {data.quota.used} interview{data.quota.used === 1 ? "" : "s"} this month ·{" "}
              {data.quota.remaining} remaining on {data.quota.plan} plan
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

        <div className="mb-8 grid grid-cols-3 gap-4">
          {[
            { label: "Interviews", value: String(data.count) },
            { label: "Best grade", value: bestGrade },
            { label: "Spend (cost)", value: `$${totalSpent.toFixed(3)}` },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-[#27272a] bg-[#111113] p-5 text-center">
              <div className="text-2xl font-bold text-[#e8e8e8] font-mono">{s.value}</div>
              <div className="mt-1 text-xs text-[#71717a]">{s.label}</div>
            </div>
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
          <div>
            <h2 className="mb-4 text-sm font-semibold text-[#e8e8e8]">Recent interviews</h2>
            {data.items.length === 0 ? (
              <div className="rounded-xl border border-[#27272a] bg-[#111113] p-8 text-center text-sm text-[#71717a]">
                No interviews yet.{" "}
                <Link href="/problems" className="text-green-400 hover:text-green-300">
                  Start one →
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {data.items.map((session) => {
                  const grade = (session.scorecard?.grade as string | undefined) ?? "";
                  const hire = (session.scorecard?.hire as string | undefined) ?? "";
                  return (
                    <div key={session.id} className="rounded-xl border border-[#27272a] bg-[#111113] p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <span className="font-medium text-[#e8e8e8] truncate">
                              {session.problem_slug ?? "Practice session"}
                            </span>
                            {session.difficulty && (
                              <span
                                className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${
                                  DIFFICULTY_COLORS[
                                    session.difficulty as keyof typeof DIFFICULTY_COLORS
                                  ] ?? ""
                                }`}
                              >
                                {session.difficulty}
                              </span>
                            )}
                            <span className="inline-flex rounded-md border border-[#27272a] px-1.5 py-0.5 text-xs text-[#71717a] capitalize">
                              {session.status}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-[#71717a]">
                            <span>{formatDate(session.started_at)}</span>
                            <span>·</span>
                            <span>{durationMin(session.started_at, session.ended_at)}</span>
                            <span>·</span>
                            <span>${session.estimated_cost_usd.toFixed(3)} cost</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {grade && (
                            <span className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border text-sm font-bold font-mono ${gradeColor(grade)}`}>
                              {grade}
                            </span>
                          )}
                          {hire && (
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${hireColor(hire)}`}>
                              {hire}
                            </span>
                          )}
                        </div>
                      </div>
                      {session.problem_slug && (
                        <div className="mt-4 flex gap-2">
                          <Link
                            href={`/problems/${session.problem_slug}`}
                            className="rounded-md border border-[#27272a] px-3 py-1.5 text-xs text-[#71717a] hover:text-[#e8e8e8] hover:border-[#3f3f46] transition-colors"
                          >
                            Retake
                          </Link>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            {user?.plan !== "pro" && (
              <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-4">
                <div className="mb-2 text-xs font-semibold text-green-400">Upgrade to Pro</div>
                <p className="mb-3 text-xs text-[#71717a] leading-relaxed">
                  Unlimited interviews, Senior &amp; Staff difficulty, and saved transcripts.
                </p>
                <Link
                  href="/pricing"
                  className="block w-full rounded-md bg-green-500 py-2 text-center text-xs font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
                >
                  See Pro plan
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
