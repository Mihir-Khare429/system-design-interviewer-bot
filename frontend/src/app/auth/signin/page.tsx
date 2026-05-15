"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAuth } from "@/lib/auth-context";

export default function SignInPage() {
  const router = useRouter();
  const { signin } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signin(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0a0a0b] px-4">
      <Link href="/" className="mb-8 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-green-500 text-[#0a0a0b] font-bold text-sm font-mono">
          SD
        </span>
        <span className="font-semibold text-[#e8e8e8]">SDI</span>
      </Link>

      <div className="w-full max-w-sm rounded-xl border border-[#27272a] bg-[#111113] p-8">
        <h1 className="mb-1 text-xl font-bold text-[#e8e8e8]">Welcome back</h1>
        <p className="mb-7 text-sm text-[#71717a]">Sign in to your account</p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#a1a1aa]">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-lg border border-[#27272a] bg-[#0a0a0b] px-3 py-2.5 text-sm text-[#e8e8e8] placeholder-[#52525b] focus:border-green-500/50 focus:outline-none focus:ring-1 focus:ring-green-500/30 transition-colors"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#a1a1aa]">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-[#27272a] bg-[#0a0a0b] px-3 py-2.5 text-sm text-[#e8e8e8] placeholder-[#52525b] focus:border-green-500/50 focus:outline-none focus:ring-1 focus:ring-green-500/30 transition-colors"
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-green-500 py-2.5 text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-[#71717a]">
          Don&apos;t have an account?{" "}
          <Link href="/auth/signup" className="text-green-400 hover:text-green-300 transition-colors">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
