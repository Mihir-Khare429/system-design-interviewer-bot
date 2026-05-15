"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function UpgradeButton({
  className,
  label = "Upgrade to Pro",
}: {
  className?: string;
  label?: string;
}) {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handle = async () => {
    if (authLoading) return;
    if (!user) {
      router.push("/auth/signup?plan=pro");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const res = await api<{ url: string }>("/api/billing/checkout", { method: "POST" });
      window.location.href = res.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start checkout");
      setPending(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <button onClick={handle} disabled={pending} className={className}>
        {pending ? "Loading…" : user?.plan === "pro" ? "Manage subscription" : label}
      </button>
      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
          {error}
        </p>
      )}
    </div>
  );
}
