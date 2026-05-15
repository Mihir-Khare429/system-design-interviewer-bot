import { Suspense } from "react";
import InterviewSession from "@/components/interview/InterviewSession";

export default function InterviewPage({
  params,
  searchParams,
}: {
  params: { sessionId: string };
  searchParams: { problem?: string; difficulty?: string };
}) {
  return (
    <Suspense fallback={<InterviewLoading />}>
      <InterviewSession
        sessionId={params.sessionId}
        problemSlug={searchParams.problem ?? "url-shortener"}
        difficulty={searchParams.difficulty ?? "Mid"}
      />
    </Suspense>
  );
}

function InterviewLoading() {
  return (
    <div className="flex h-screen items-center justify-center bg-[#0a0a0b]">
      <div className="text-center">
        <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-[#27272a] border-t-green-500 mx-auto" />
        <p className="text-sm text-[#71717a]">Setting up your interview…</p>
      </div>
    </div>
  );
}
