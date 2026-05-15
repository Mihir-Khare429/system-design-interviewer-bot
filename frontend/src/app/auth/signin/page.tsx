import Link from "next/link";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0a0a0b] px-4">
      {/* Logo */}
      <Link href="/" className="mb-8 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-green-500 text-[#0a0a0b] font-bold text-sm font-mono">
          SD
        </span>
        <span className="font-semibold text-[#e8e8e8]">SDI</span>
      </Link>

      <div className="w-full max-w-sm rounded-xl border border-[#27272a] bg-[#111113] p-8">
        <h1 className="mb-1 text-xl font-bold text-[#e8e8e8]">Welcome back</h1>
        <p className="mb-7 text-sm text-[#71717a]">Sign in to your account</p>

        {/* Google OAuth */}
        <button className="mb-4 flex w-full items-center justify-center gap-3 rounded-lg border border-[#27272a] bg-[#18181b] py-2.5 text-sm text-[#e8e8e8] hover:border-[#3f3f46] hover:bg-[#1c1c1e] transition-colors">
          <svg className="h-4 w-4" viewBox="0 0 24 24">
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          Continue with Google
        </button>

        <div className="relative mb-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[#27272a]" />
          </div>
          <div className="relative flex justify-center text-xs text-[#52525b]">
            <span className="bg-[#111113] px-2">or continue with email</span>
          </div>
        </div>

        <form className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#a1a1aa]">Email</label>
            <input
              type="email"
              placeholder="you@example.com"
              className="w-full rounded-lg border border-[#27272a] bg-[#0a0a0b] px-3 py-2.5 text-sm text-[#e8e8e8] placeholder-[#52525b] focus:border-green-500/50 focus:outline-none focus:ring-1 focus:ring-green-500/30 transition-colors"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#a1a1aa]">Password</label>
            <input
              type="password"
              placeholder="••••••••"
              className="w-full rounded-lg border border-[#27272a] bg-[#0a0a0b] px-3 py-2.5 text-sm text-[#e8e8e8] placeholder-[#52525b] focus:border-green-500/50 focus:outline-none focus:ring-1 focus:ring-green-500/30 transition-colors"
            />
            <div className="mt-1.5 text-right">
              <Link href="#" className="text-xs text-[#71717a] hover:text-[#e8e8e8] transition-colors">
                Forgot password?
              </Link>
            </div>
          </div>

          <button
            type="submit"
            className="w-full rounded-lg bg-green-500 py-2.5 text-sm font-semibold text-[#0a0a0b] hover:bg-green-400 transition-colors"
          >
            Sign in
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
