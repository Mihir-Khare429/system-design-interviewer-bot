import { notFound } from "next/navigation";
import Link from "next/link";
import Navbar from "@/components/layout/Navbar";
import { getProblemBySlug, PROBLEMS, DIFFICULTY_COLORS, CATEGORY_ICONS } from "@/lib/problems";
import StartInterviewButton from "@/components/interview/StartInterviewButton";

export function generateStaticParams() {
  return PROBLEMS.map((p) => ({ slug: p.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }) {
  const problem = getProblemBySlug(params.slug);
  if (!problem) return {};
  return {
    title: `${problem.title} — SDI`,
    description: problem.brief,
  };
}

export default function ProblemDetailPage({ params }: { params: { slug: string } }) {
  const problem = getProblemBySlug(params.slug);
  if (!problem) notFound();

  return (
    <div className="min-h-screen bg-[#0a0a0b]">
      <Navbar />

      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        {/* Breadcrumb */}
        <nav className="mb-6 flex items-center gap-2 text-sm text-[#71717a]">
          <Link href="/problems" className="hover:text-[#e8e8e8] transition-colors">
            Problems
          </Link>
          <span>/</span>
          <span className="text-[#e8e8e8]">{problem.title}</span>
        </nav>

        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          {/* Left: problem description */}
          <div>
            <div className="rounded-xl border border-[#27272a] bg-[#111113] p-6 sm:p-8">
              {/* Header */}
              <div className="mb-6">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="text-lg">{CATEGORY_ICONS[problem.category]}</span>
                  <span className="text-xs text-[#71717a]">{problem.category}</span>
                  <span className="text-[#3f3f46]">·</span>
                  {problem.difficulty.map((d) => (
                    <span
                      key={d}
                      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLORS[d]}`}
                    >
                      {d}
                    </span>
                  ))}
                </div>
                <h1 className="text-xl font-bold text-[#e8e8e8] sm:text-2xl">{problem.title}</h1>
                <p className="mt-2 text-[#71717a]">{problem.brief}</p>
              </div>

              {/* Divider */}
              <div className="mb-6 border-t border-[#27272a]" />

              {/* Full problem statement */}
              <div className="prose-sdi">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-[#71717a]">
                  Problem Statement
                </h2>
                <pre className="whitespace-pre-wrap rounded-lg border border-[#27272a] bg-[#0a0a0b] p-4 font-mono text-sm text-[#e8e8e8] leading-relaxed">
                  {problem.full}
                </pre>
              </div>

              {/* Tags */}
              <div className="mt-6">
                <h2 className="mb-3 text-xs font-medium uppercase tracking-widest text-[#71717a]">
                  Technologies
                </h2>
                <div className="flex flex-wrap gap-2">
                  {problem.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-md bg-[#27272a] px-2.5 py-1 text-xs text-[#a1a1aa]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Right: start interview card */}
          <div>
            <div className="sticky top-20 rounded-xl border border-[#27272a] bg-[#111113] p-6">
              <h2 className="mb-4 font-semibold text-[#e8e8e8]">Start Interview</h2>

              {/* Quick stats */}
              <div className="mb-5 space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-[#71717a]">Estimated time</span>
                  <span className="font-mono text-[#e8e8e8]">{problem.estimatedTime}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[#71717a]">Interview phases</span>
                  <span className="text-[#e8e8e8]">4</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[#71717a]">Asked at</span>
                  <span className="text-[#e8e8e8] text-right text-xs">
                    {problem.companies.join(", ")}
                  </span>
                </div>
              </div>

              <div className="mb-5 border-t border-[#27272a]" />

              {/* Difficulty selector */}
              <div className="mb-5">
                <label className="mb-2 block text-xs font-medium text-[#71717a]">
                  Difficulty level
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {problem.difficulty.map((d) => (
                    <label
                      key={d}
                      className="flex cursor-pointer items-center gap-2 rounded-lg border border-[#27272a] p-2.5 hover:border-[#3f3f46] transition-colors has-[:checked]:border-green-500/40 has-[:checked]:bg-green-500/5"
                    >
                      <input
                        type="radio"
                        name="difficulty"
                        value={d}
                        defaultChecked={d === problem.difficulty[0]}
                        className="h-3.5 w-3.5 accent-green-500"
                      />
                      <span className={`text-xs font-medium ${DIFFICULTY_COLORS[d].split(" ")[0]}`}>
                        {d}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* CTA */}
              <StartInterviewButton slug={problem.slug} />

              <p className="mt-3 text-center text-xs text-[#52525b]">
                Voice + canvas interview · ~{problem.estimatedTime}
              </p>
            </div>

            {/* What to expect */}
            <div className="mt-4 rounded-xl border border-[#27272a] bg-[#111113] p-5">
              <h3 className="mb-4 text-xs font-semibold uppercase tracking-widest text-[#71717a]">
                What to expect
              </h3>
              <ul className="space-y-3 text-sm text-[#71717a]">
                {[
                  { icon: "💬", text: "Warm-up: background and experience" },
                  { icon: "❓", text: "Constraints: clarify the problem" },
                  { icon: "🏗️", text: "Design: draw & explain your architecture" },
                  { icon: "⚔️", text: "Deep dive: adversarial probes & trade-offs" },
                  { icon: "📊", text: "Scorecard: grade, gaps, study plan" },
                ].map(({ icon, text }) => (
                  <li key={text} className="flex items-start gap-2">
                    <span>{icon}</span>
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
