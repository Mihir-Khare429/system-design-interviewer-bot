"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";

export default function StartInterviewButton({ slug }: { slug: string }) {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);

  const handleStart = () => {
    if (authLoading) return;
    if (!user) {
      router.push(`/auth/signin?redirect=/problems/${slug}`);
      return;
    }
    setLoading(true);
    const form = document.querySelector<HTMLInputElement>('input[name="difficulty"]:checked');
    const difficulty = form?.value ?? "Mid";
    const sessionId = `${slug}-${Date.now()}`;
    router.push(
      `/interview/${sessionId}?problem=${slug}&difficulty=${encodeURIComponent(difficulty)}`
    );
  };

  return (
    <button
      onClick={handleStart}
      disabled={loading || authLoading}
      className="flex w-full items-center justify-center gap-2 rounded-lg bg-green-500 py-3 text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 disabled:opacity-60 transition-colors"
    >
      {loading ? (
        <>
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          Starting session…
        </>
      ) : !user && !authLoading ? (
        <>Sign in to start</>
      ) : (
        <>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
          Start interview
        </>
      )}
    </button>
  );
}
