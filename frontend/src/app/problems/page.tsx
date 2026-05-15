"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import Navbar from "@/components/layout/Navbar";
import {
  PROBLEMS,
  DIFFICULTY_COLORS,
  CATEGORY_ICONS,
  type Category,
  type Difficulty,
} from "@/lib/problems";

const CATEGORIES: Category[] = [
  "Storage",
  "Distributed",
  "Real-time",
  "Messaging",
  "Search",
  "ML",
  "Payments",
  "Social",
];

const DIFFICULTIES: Difficulty[] = ["Junior", "Mid", "Senior", "Staff"];

export default function ProblemsPage() {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<Category | "All">("All");
  const [activeDifficulty, setActiveDifficulty] = useState<Difficulty | "All">("All");

  const filtered = useMemo(() => {
    let results = [...PROBLEMS];
    if (activeCategory !== "All") {
      results = results.filter((p) => p.category === activeCategory);
    }
    if (activeDifficulty !== "All") {
      results = results.filter((p) => p.difficulty.includes(activeDifficulty));
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      results = results.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.tags.some((t) => t.toLowerCase().includes(q)) ||
          p.brief.toLowerCase().includes(q)
      );
    }
    return results;
  }, [search, activeCategory, activeDifficulty]);

  return (
    <div className="min-h-screen bg-[#0a0a0b]">
      <Navbar />

      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#e8e8e8]">Problems</h1>
          <p className="mt-1 text-sm text-[#71717a]">
            {PROBLEMS.length} system design problems calibrated to FAANG standards
          </p>
        </div>

        {/* Search + Filters */}
        <div className="mb-6 flex flex-col gap-4">
          {/* Search */}
          <div className="relative">
            <svg
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#71717a]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 104.5 4.5a7.5 7.5 0 0012.15 12.15z"
              />
            </svg>
            <input
              type="text"
              placeholder="Search problems, technologies…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-[#27272a] bg-[#111113] py-2.5 pl-10 pr-4 text-sm text-[#e8e8e8] placeholder-[#52525b] focus:border-green-500/50 focus:outline-none focus:ring-1 focus:ring-green-500/30 transition-colors"
            />
          </div>

          {/* Category filter */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setActiveCategory("All")}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                activeCategory === "All"
                  ? "border-green-500/40 bg-green-500/10 text-green-400"
                  : "border-[#27272a] text-[#71717a] hover:border-[#3f3f46] hover:text-[#e8e8e8]"
              }`}
            >
              All topics
            </button>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat === activeCategory ? "All" : cat)}
                className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeCategory === cat
                    ? "border-green-500/40 bg-green-500/10 text-green-400"
                    : "border-[#27272a] text-[#71717a] hover:border-[#3f3f46] hover:text-[#e8e8e8]"
                }`}
              >
                {CATEGORY_ICONS[cat]} {cat}
              </button>
            ))}
          </div>

          {/* Difficulty filter */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setActiveDifficulty("All")}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                activeDifficulty === "All"
                  ? "border-[#3f3f46] bg-white/10 text-[#e8e8e8]"
                  : "border-[#27272a] text-[#71717a] hover:border-[#3f3f46]"
              }`}
            >
              All levels
            </button>
            {DIFFICULTIES.map((d) => (
              <button
                key={d}
                onClick={() => setActiveDifficulty(d === activeDifficulty ? "All" : d)}
                className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeDifficulty === d
                    ? DIFFICULTY_COLORS[d]
                    : "border-[#27272a] text-[#71717a] hover:border-[#3f3f46]"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* Results count */}
        <div className="mb-4 text-xs text-[#71717a]">
          {filtered.length} problem{filtered.length !== 1 ? "s" : ""}
          {activeCategory !== "All" || activeDifficulty !== "All" || search ? " matching filters" : ""}
        </div>

        {/* Problem list — LeetCode-style table */}
        <div className="rounded-xl border border-[#27272a] bg-[#111113] overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-4 border-b border-[#27272a] px-5 py-3 text-xs font-medium text-[#71717a] hidden sm:grid">
            <span>Title</span>
            <span className="text-right">Difficulty</span>
            <span className="text-right">Category</span>
            <span className="text-right">Time</span>
          </div>

          {filtered.length === 0 ? (
            <div className="py-20 text-center text-sm text-[#71717a]">
              No problems match your filters.
            </div>
          ) : (
            <ul className="divide-y divide-[#27272a]">
              {filtered.map((problem, idx) => (
                <li key={problem.slug}>
                  <Link
                    href={`/problems/${problem.slug}`}
                    className="group flex flex-col gap-3 px-5 py-4 hover:bg-[#18181b] transition-colors sm:grid sm:grid-cols-[1fr_auto_auto_auto] sm:items-center sm:gap-4"
                  >
                    {/* Title + tags */}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-[#52525b]">
                          {String(idx + 1).padStart(2, "0")}
                        </span>
                        <span className="font-medium text-[#e8e8e8] group-hover:text-white transition-colors">
                          {problem.title}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1.5 pl-7">
                        {problem.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-[#27272a] px-1.5 py-0.5 text-xs text-[#71717a]"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Difficulty badges */}
                    <div className="flex flex-wrap gap-1 pl-7 sm:pl-0 sm:justify-end">
                      {problem.difficulty.map((d) => (
                        <span
                          key={d}
                          className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLORS[d]}`}
                        >
                          {d}
                        </span>
                      ))}
                    </div>

                    {/* Category */}
                    <span className="hidden sm:flex items-center gap-1.5 text-xs text-[#71717a] justify-end">
                      <span>{CATEGORY_ICONS[problem.category]}</span>
                      {problem.category}
                    </span>

                    {/* Time */}
                    <span className="hidden sm:block text-xs text-[#71717a] text-right font-mono">
                      {problem.estimatedTime}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
