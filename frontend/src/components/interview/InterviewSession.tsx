"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import ArchitectureCanvas from "./ArchitectureCanvas";
import { getProblemBySlug, DIFFICULTY_COLORS } from "@/lib/problems";
import { getToken } from "@/lib/api";

type Phase = "INTRO" | "CONSTRAINTS" | "DESIGN" | "DEEP_DIVE" | "DONE";
type Message = { role: "user" | "assistant"; content: string; timestamp: number };

const PHASE_LABELS: Record<Phase, string> = {
  INTRO: "Intro",
  CONSTRAINTS: "Constraints",
  DESIGN: "Design",
  DEEP_DIVE: "Deep Dive",
  DONE: "Complete",
};

const PHASE_COLORS: Record<Phase, string> = {
  INTRO: "text-indigo-400 bg-indigo-400/10 border-indigo-400/20",
  CONSTRAINTS: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  DESIGN: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  DEEP_DIVE: "text-red-400 bg-red-400/10 border-red-400/20",
  DONE: "text-green-400 bg-green-400/10 border-green-400/20",
};

const WS_URL = process.env.NEXT_PUBLIC_API_URL ?? "ws://localhost:8000";

export default function InterviewSession({
  sessionId,
  problemSlug,
  difficulty,
}: {
  sessionId: string;
  problemSlug: string;
  difficulty: string;
}) {
  const problem = getProblemBySlug(problemSlug);

  const [phase, setPhase] = useState<Phase>("INTRO");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [alexSpeaking, setAlexSpeaking] = useState(false);
  const [connected, setConnected] = useState(false);
  const [scorecard, setScorecard] = useState<ScorecardData | null>(null);
  const [showCanvas, setShowCanvas] = useState(true);
  const [endingState, setEndingState] = useState<"idle" | "ending" | "scoring">("idle");
  const [endError, setEndError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioQueueRef = useRef<string[]>([]);
  const audioPlayingRef = useRef(false);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // ── WebSocket ────────────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    const token = getToken() ?? "";
    const url =
      `${WS_URL.replace(/^http/, "ws")}/ws/interview` +
      `?topic=${encodeURIComponent(problem?.category ?? "")}` +
      `&difficulty=${encodeURIComponent(difficulty)}` +
      `&problem=${encodeURIComponent(problemSlug)}` +
      `&token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); wsRef.current = null; };

    ws.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);

      if (msg.type === "session_started") {
        setPhase(msg.phase ?? "INTRO");
      }
      if (msg.type === "phase_change") {
        setPhase(msg.phase as Phase);
      }
      if (msg.type === "transcript") {
        setMessages((prev) => [
          ...prev,
          { role: "user", content: msg.text, timestamp: Date.now() },
        ]);
      }
      if (msg.type === "response") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: msg.text, timestamp: Date.now() },
        ]);
        if (msg.audio) {
          queueAudio(msg.audio);
        }
      }
      if (msg.type === "interrupt") {
        stopCurrentAudio();
      }
      if (msg.type === "scorecard_loading") {
        setEndingState("scoring");
      }
      if (msg.type === "scorecard") {
        setPhase("DONE");
        setEndingState("idle");
        try {
          const parsed = typeof msg.data === "string" ? JSON.parse(msg.data) : msg.data;
          setScorecard(parsed as ScorecardData);
        } catch {
          setScorecard({ summary: String(msg.data) });
        }
      }
      if (msg.type === "error" || msg.type === "quota_exceeded") {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: msg.message ?? "Session could not start.",
            timestamp: Date.now(),
          },
        ]);
      }
    };
  }, [problem, difficulty, problemSlug]);

  useEffect(() => {
    connect();
    return () => { wsRef.current?.close(); };
  }, [connect]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Audio playback ───────────────────────────────────────────────────────────

  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      audioPlayingRef.current = false;
      setAlexSpeaking(false);
      return;
    }
    const b64 = audioQueueRef.current.shift()!;
    audioPlayingRef.current = true;
    setAlexSpeaking(true);

    const audio = new Audio(`data:audio/mp3;base64,${b64}`);
    audio.onended = playNextInQueue;
    audio.onerror = playNextInQueue;
    audio.play().catch(() => playNextInQueue());
  }, []);

  const queueAudio = useCallback(
    (b64: string) => {
      audioQueueRef.current.push(b64);
      if (!audioPlayingRef.current) playNextInQueue();
    },
    [playNextInQueue]
  );

  const stopCurrentAudio = () => {
    audioQueueRef.current = [];
    audioPlayingRef.current = false;
    setAlexSpeaking(false);
  };

  // ── Push-to-talk recording ───────────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    if (isRecording || !connected) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const reader = new FileReader();
        reader.onloadend = () => {
          const b64 = (reader.result as string).split(",")[1];
          wsRef.current?.send(JSON.stringify({ type: "audio", data: b64, mime: "audio/webm" }));
        };
        reader.readAsDataURL(blob);
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setIsRecording(true);
    } catch (err) {
      console.error("Mic access denied:", err);
    }
  }, [isRecording, connected]);

  const stopRecording = useCallback(() => {
    if (!isRecording) return;
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setIsRecording(false);
  }, [isRecording]);

  // Keyboard shortcut: Space
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        startRecording();
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") stopRecording();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => { window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp); };
  }, [startRecording, stopRecording]);

  const sendEndInterview = () => {
    if (endingState !== "idle") return;
    setEndError(null);

    if (isRecording) stopRecording();
    stopCurrentAudio();

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setEndError("Not connected. Refresh the page and try again.");
      return;
    }
    try {
      ws.send(JSON.stringify({ type: "end" }));
      setEndingState("ending");
    } catch {
      setEndError("Could not send end-interview signal.");
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  if (scorecard) {
    return <ScorecardView scorecard={scorecard} problemSlug={problemSlug} />;
  }

  return (
    <div className="relative flex h-screen flex-col bg-[#0a0a0b] overflow-hidden">
      {/* Scoring overlay */}
      {endingState !== "idle" && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#0a0a0b]/85 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4 rounded-xl border border-[#27272a] bg-[#111113] px-8 py-6 max-w-sm text-center">
            <svg className="h-6 w-6 animate-spin text-green-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            <div>
              <div className="text-sm font-medium text-[#e8e8e8]">
                {endingState === "ending" ? "Ending interview…" : "Generating scorecard…"}
              </div>
              <div className="mt-1 text-xs text-[#71717a]">This usually takes 5–20 seconds.</div>
            </div>
          </div>
        </div>
      )}
      {endError && (
        <div className="absolute top-14 left-1/2 z-40 -translate-x-1/2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {endError}
        </div>
      )}
      {/* Top bar */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-[#27272a] px-4">
        <div className="flex items-center gap-3">
          <Link href="/problems" className="text-[#71717a] hover:text-[#e8e8e8] transition-colors">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <span className="text-sm font-medium text-[#e8e8e8] hidden sm:block">
            {problem?.title ?? "Interview"}
          </span>
          {problem && (
            <span className={`hidden sm:inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLORS[difficulty as keyof typeof DIFFICULTY_COLORS] ?? "text-[#71717a] border-[#27272a]"}`}>
              {difficulty}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Phase badge */}
          <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${PHASE_COLORS[phase]}`}>
            {PHASE_LABELS[phase]}
          </span>

          {/* Connection indicator */}
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`} title={connected ? "Connected" : "Disconnected"} />

          {/* Canvas toggle */}
          <button
            onClick={() => setShowCanvas((v) => !v)}
            className="rounded-md border border-[#27272a] px-2.5 py-1 text-xs text-[#71717a] hover:text-[#e8e8e8] hover:border-[#3f3f46] transition-colors"
          >
            {showCanvas ? "Hide canvas" : "Show canvas"}
          </button>

          {/* End interview */}
          <button
            onClick={sendEndInterview}
            disabled={endingState !== "idle"}
            className="rounded-md border border-red-500/20 bg-red-500/5 px-2.5 py-1 text-xs text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {endingState === "idle" ? "End interview" : endingState === "ending" ? "Ending…" : "Scoring…"}
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Canvas */}
        {showCanvas && (
          <div className="hidden lg:flex flex-1 border-r border-[#27272a]">
            <ArchitectureCanvas />
          </div>
        )}

        {/* Transcript + controls */}
        <div className={`flex flex-col ${showCanvas ? "w-full lg:w-[380px]" : "w-full max-w-2xl mx-auto"} shrink-0`}>
          {/* Alex speaking indicator */}
          {alexSpeaking && (
            <div className="border-b border-[#27272a] bg-[#111113] px-4 py-2 flex items-center gap-2">
              <div className="flex items-center gap-0.5">
                {[...Array(4)].map((_, i) => (
                  <div
                    key={i}
                    className="w-0.5 rounded-full bg-green-400 animate-bounce"
                    style={{ height: `${8 + (i % 2) * 8}px`, animationDelay: `${i * 0.1}s` }}
                  />
                ))}
              </div>
              <span className="text-xs text-green-400">Alex is speaking…</span>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="mb-3 text-3xl">🎙️</div>
                <p className="text-sm text-[#71717a]">
                  {connected
                    ? "Hold Space (or the mic button) to speak."
                    : "Connecting to interviewer…"}
                </p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "assistant" && (
                  <div className="mr-2 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-green-500 text-[#0a0a0b] text-xs font-bold">
                    A
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "rounded-tr-sm bg-[#27272a] text-[#e8e8e8]"
                      : "rounded-tl-sm bg-[#111113] border border-[#27272a] text-[#e8e8e8]"
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>

          {/* Controls */}
          <div className="shrink-0 border-t border-[#27272a] bg-[#0a0a0b] p-4">
            <div className="flex items-center gap-3">
              {/* Mic button */}
              <button
                onPointerDown={startRecording}
                onPointerUp={stopRecording}
                onPointerLeave={stopRecording}
                disabled={!connected}
                className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition-all ${
                  isRecording
                    ? "bg-red-500 scale-110 shadow-lg shadow-red-500/30"
                    : "border border-[#27272a] bg-[#111113] text-[#71717a] hover:border-[#3f3f46] hover:text-[#e8e8e8]"
                } disabled:opacity-40`}
                aria-label={isRecording ? "Recording — release to send" : "Hold to record"}
              >
                {isRecording ? (
                  <span className="h-3 w-3 rounded-sm bg-white" />
                ) : (
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3zm-1 14.93A7.001 7.001 0 015 9H3a9 9 0 008 8.94V20H8v2h8v-2h-3v-2.07A9 9 0 0021 9h-2a7 7 0 01-6 6.93z" />
                  </svg>
                )}
              </button>

              <div className="flex-1 text-xs text-[#52525b] text-center">
                {isRecording
                  ? "🔴 Recording — release to send"
                  : connected
                  ? "Hold mic or Space bar to speak"
                  : "Connecting…"}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Scorecard ────────────────────────────────────────────────────────────────

type ScorecardData = Record<string, string>;

function ScorecardView({
  scorecard,
  problemSlug,
}: {
  scorecard: ScorecardData;
  problemSlug: string;
}) {
  const grade = scorecard.grade ?? "";
  const gradeColor =
    grade?.startsWith("A") ? "text-green-400 border-green-400/30 bg-green-400/5"
    : grade?.startsWith("B") ? "text-blue-400 border-blue-400/30 bg-blue-400/5"
    : grade?.startsWith("C") ? "text-yellow-400 border-yellow-400/30 bg-yellow-400/5"
    : "text-red-400 border-red-400/30 bg-red-400/5";

  const hireColor =
    String(scorecard.hire).includes("Strong Yes") ? "bg-green-500/10 text-green-400"
    : String(scorecard.hire).includes("Yes") ? "bg-blue-500/10 text-blue-400"
    : "bg-red-500/10 text-red-400";

  return (
    <div className="min-h-screen bg-[#0a0a0b] px-4 py-12 sm:px-6">
      <div className="mx-auto max-w-2xl">
        <div className="mb-8 flex items-center justify-between">
          <Link href="/problems" className="text-sm text-[#71717a] hover:text-[#e8e8e8]">
            ← Back to problems
          </Link>
          <Link
            href={`/problems/${problemSlug}`}
            className="rounded-lg border border-[#27272a] px-3 py-1.5 text-sm text-[#71717a] hover:text-[#e8e8e8] hover:border-[#3f3f46] transition-colors"
          >
            Try again
          </Link>
        </div>

        <div className="rounded-xl border border-[#27272a] bg-[#111113] p-8">
          {/* Grade + hire */}
          <div className="mb-8 flex items-center gap-4">
            <div className={`flex h-16 w-16 items-center justify-center rounded-xl border-2 text-3xl font-bold font-mono ${gradeColor}`}>
              {grade ?? "–"}
            </div>
            <div>
              <div className="mb-1 text-lg font-bold text-[#e8e8e8]">Interview complete</div>
              {scorecard.hire && (
                <span className={`inline-block rounded-full px-3 py-0.5 text-sm font-medium ${hireColor}`}>
                  {String(scorecard.hire)}
                </span>
              )}
            </div>
          </div>

          {/* Summary */}
          {scorecard.summary && (
            <div className="mb-6">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-[#71717a]">
                Summary
              </h3>
              <p className="text-sm text-[#a1a1aa] leading-relaxed">{String(scorecard.summary)}</p>
            </div>
          )}

          {/* Strengths / Gaps */}
          <div className="mb-6 grid gap-4 sm:grid-cols-2">
            {scorecard.strengths && (
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-green-400">
                  Strengths
                </h3>
                <p className="text-sm text-[#a1a1aa] leading-relaxed">{String(scorecard.strengths)}</p>
              </div>
            )}
            {scorecard.gaps && (
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-red-400">
                  Gaps
                </h3>
                <p className="text-sm text-[#a1a1aa] leading-relaxed">{String(scorecard.gaps)}</p>
              </div>
            )}
          </div>

          {/* Study topics */}
          {scorecard.study && (
            <div className="rounded-lg border border-[#27272a] bg-[#0a0a0b] p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-[#71717a]">
                Study topics
              </h3>
              <p className="text-sm text-[#a1a1aa] leading-relaxed">{String(scorecard.study)}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
