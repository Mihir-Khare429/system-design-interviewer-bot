"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/problems", label: "Problems" },
  { href: "/pricing", label: "Pricing" },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-[#27272a] bg-[#0a0a0b]/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 group">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-green-500 text-[#0a0a0b] font-bold text-sm font-mono">
            SD
          </span>
          <span className="font-semibold text-[#e8e8e8] text-sm tracking-tight hidden sm:block">
            SDI
          </span>
        </Link>

        {/* Nav */}
        <nav className="flex items-center gap-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                pathname.startsWith(link.href)
                  ? "text-[#e8e8e8] bg-white/10"
                  : "text-[#71717a] hover:text-[#e8e8e8] hover:bg-white/5"
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Auth */}
        <div className="flex items-center gap-2">
          <Link
            href="/auth/signin"
            className="px-3 py-1.5 text-sm text-[#71717a] hover:text-[#e8e8e8] transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/auth/signup"
            className="px-3 py-1.5 text-sm font-medium rounded-md bg-green-500 text-[#0a0a0b] hover:bg-green-400 transition-colors"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}
