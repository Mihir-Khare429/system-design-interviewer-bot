"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import ArchitectureCanvas, { type ArchitectureSnapshot } from "./ArchitectureCanvas";
import { getProblemBySlug, DIFFICULTY_COLORS } from "@/lib/problems";
import { getToken } from "@/lib/api";

type Phase = "INTRO" | "CONSTRAINTS" | "DESIGN" | "DEEP_DIVE" | "DONE";
type Message = { role: "user" | "assistant"; content: string; timestamp: number };
type AudioPipelineState =
  | "idle"
  | "starting"
  | "recording"
  | "uploading"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "scoring"
  | "error";

type BrowserSpeechRecognitionResult = {
  isFinal: boolean;
  0: { transcript: string };
};

type BrowserSpeechRecognitionEvent = Event & {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: BrowserSpeechRecognitionResult;
  };
};

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

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

const AUDIO_PIPELINE_LABELS: Record<AudioPipelineState, string> = {
  idle: "Ready",
  starting: "Opening microphone…",
  recording: "Recording…",
  uploading: "Uploading audio…",
  transcribing: "Transcribing audio…",
  thinking: "Alex is thinking…",
  speaking: "Alex is speaking…",
  scoring: "Generating scorecard…",
  error: "Audio pipeline needs attention",
};

const AUDIO_PIPELINE_PROGRESS: Record<AudioPipelineState, string> = {
  idle: "0%",
  starting: "12%",
  recording: "28%",
  uploading: "45%",
  transcribing: "62%",
  thinking: "78%",
  speaking: "92%",
  scoring: "86%",
  error: "100%",
};

const WS_URL = process.env.NEXT_PUBLIC_API_URL ?? "ws://localhost:8000";

function getSpeechRecognitionCtor(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const speechWindow = window as unknown as {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

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
  const [liveTranscript, setLiveTranscript] = useState("");
  const [alexSpeaking, setAlexSpeaking] = useState(false);
  const [connected, setConnected] = useState(false);
  const [liveMode, setLiveMode] = useState(false);
  const [scorecard, setScorecard] = useState<ScorecardData | null>(null);
  const [showCanvas, setShowCanvas] = useState(true);
  const [endingState, setEndingState] = useState<"idle" | "ending" | "scoring">("idle");
  const [endError, setEndError] = useState<string | null>(null);
  const [audioStatus, setAudioStatus] = useState<AudioPipelineState>("idle");
  const [audioError, setAudioError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioQueueRef = useRef<string[]>([]);
  const audioPlayingRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioStatusRef = useRef<AudioPipelineState>("idle");
  const connectedRef = useRef(false);
  const isRecordingRef = useRef(false);
  const endingStateRef = useRef<"idle" | "ending" | "scoring">("idle");
  const recordingStartPendingRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const pendingEndRef = useRef(false);
  const liveModeRef = useRef(false);
  const liveStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const vadFrameRef = useRef<number | null>(null);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechRecognitionRunningRef = useRef(false);
  const speechRecognitionSessionRef = useRef(0);
  const finalSpeechTextRef = useRef("");
  const lastSpeechAtRef = useRef(0);
  const recordingStartedAtRef = useRef(0);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  const setAudioPipeline = useCallback((state: AudioPipelineState, error?: string) => {
    audioStatusRef.current = state;
    setAudioStatus(state);
    if (error) {
      setAudioError(error);
    } else if (state !== "error") {
      setAudioError(null);
    }
  }, []);

  // ── WebSocket ────────────────────────────────────────────────────────────────

  const connect = useCallback((): WebSocket => {
    const token = getToken() ?? "";
    const url =
      `${WS_URL.replace(/^http/, "ws")}/ws/interview` +
      `?topic=${encodeURIComponent(problem?.category ?? "")}` +
      `&difficulty=${encodeURIComponent(difficulty)}` +
      `&problem=${encodeURIComponent(problemSlug)}` +
      `&token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      setConnected(true);
      setAudioPipeline("idle");
    };
    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      setConnected(false);
      wsRef.current = null;
      if (
        audioStatusRef.current !== "idle" &&
        audioStatusRef.current !== "error" &&
        endingStateRef.current === "idle"
      ) {
        setAudioPipeline("error", "Connection closed before audio processing finished.");
      }
    };

    ws.onmessage = async (ev) => {
      if (wsRef.current !== ws) return;
      const msg = JSON.parse(ev.data);

      if (msg.type === "session_started") {
        setPhase(msg.phase ?? "INTRO");
      }
      if (msg.type === "audio_received") {
        setAudioPipeline("transcribing");
      }
      if (msg.type === "processing_state") {
        const nextState = msg.state as AudioPipelineState;
        if (nextState === "idle" && audioPlayingRef.current) {
          return;
        }
        if (nextState in AUDIO_PIPELINE_LABELS) {
          setAudioPipeline(nextState, msg.message);
        }
      }
      if (msg.type === "phase_change") {
        setPhase(msg.phase as Phase);
      }
      if (msg.type === "transcript") {
        setAudioPipeline("thinking");
        if (!isRecordingRef.current) {
          speechRecognitionSessionRef.current += 1;
          finalSpeechTextRef.current = "";
          setLiveTranscript("");
        }
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
        setAudioPipeline("speaking");
        if (msg.audio) {
          queueAudio(msg.audio);
        }
      }
      if (msg.type === "response_audio" && msg.audio) {
        setAudioPipeline("speaking");
        queueAudio(msg.audio);
      }
      if (msg.type === "interrupt") {
        stopCurrentAudio();
      }
      if (msg.type === "scorecard_loading") {
        setEndingState("scoring");
        setAudioPipeline("scoring");
      }
      if (msg.type === "scorecard") {
        setPhase("DONE");
        setEndingState("idle");
        setAudioPipeline("idle");
        try {
          const parsed = typeof msg.data === "string" ? JSON.parse(msg.data) : msg.data;
          setScorecard(parsed as ScorecardData);
        } catch {
          setScorecard({ summary: String(msg.data) });
        }
      }
      if (msg.type === "error" || msg.type === "quota_exceeded") {
        setAudioPipeline("error", msg.message ?? "Session could not start.");
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
    return ws;
  }, [problem, difficulty, problemSlug]);

  useEffect(() => {
    const ws = connect();
    return () => {
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      ws.close();
    };
  }, [connect]);

  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  useEffect(() => {
    liveModeRef.current = liveMode;
  }, [liveMode]);

  useEffect(() => {
    endingStateRef.current = endingState;
  }, [endingState]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveTranscript]);

  // ── Audio playback ───────────────────────────────────────────────────────────

  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      audioPlayingRef.current = false;
      currentAudioRef.current = null;
      setAlexSpeaking(false);
      if (audioStatusRef.current === "speaking") {
        setAudioPipeline("idle");
      }
      return;
    }
    const b64 = audioQueueRef.current.shift()!;
    audioPlayingRef.current = true;
    setAlexSpeaking(true);
    setAudioPipeline("speaking");

    const audio = new Audio(`data:audio/mp3;base64,${b64}`);
    currentAudioRef.current = audio;
    audio.onended = playNextInQueue;
    audio.onerror = playNextInQueue;
    audio.play().catch(() => playNextInQueue());
  }, [setAudioPipeline]);

  const queueAudio = useCallback(
    (b64: string) => {
      audioQueueRef.current.push(b64);
      setAudioPipeline("speaking");
      if (!audioPlayingRef.current) playNextInQueue();
    },
    [playNextInQueue, setAudioPipeline]
  );

  const stopCurrentAudio = useCallback(() => {
    audioQueueRef.current = [];
    const audio = currentAudioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      currentAudioRef.current = null;
    }
    audioPlayingRef.current = false;
    setAlexSpeaking(false);
    if (audioStatusRef.current === "speaking") {
      setAudioPipeline("idle");
    }
  }, [setAudioPipeline]);

  // ── Realtime speech capture ─────────────────────────────────────────────────

  const recorderMime = () =>
    typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";

  const sendSpeechStart = useCallback(() => {
    stopCurrentAudio();
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "speech_start" }));
    }
  }, [stopCurrentAudio]);

  const clearLiveTranscriptDraft = useCallback(() => {
    speechRecognitionSessionRef.current += 1;
    finalSpeechTextRef.current = "";
    setLiveTranscript("");
  }, []);

  const stopLiveTranscription = useCallback(() => {
    const recognition = speechRecognitionRef.current;
    if (!recognition || !speechRecognitionRunningRef.current) return;
    try {
      recognition.stop();
    } catch {
      speechRecognitionRunningRef.current = false;
    }
  }, []);

  const abortLiveTranscription = useCallback(() => {
    const recognition = speechRecognitionRef.current;
    if (recognition && speechRecognitionRunningRef.current) {
      try {
        recognition.abort();
      } catch {
        // Browser recognizers can throw when aborting during startup.
      }
    }
    speechRecognitionRunningRef.current = false;
    clearLiveTranscriptDraft();
  }, [clearLiveTranscriptDraft]);

  const startLiveTranscription = useCallback(() => {
    const Recognition = getSpeechRecognitionCtor();
    if (!Recognition || speechRecognitionRunningRef.current) return;

    const sessionId = speechRecognitionSessionRef.current + 1;
    speechRecognitionSessionRef.current = sessionId;
    finalSpeechTextRef.current = "";
    setLiveTranscript("");

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      if (speechRecognitionSessionRef.current !== sessionId) return;

      let interim = "";
      let finalText = finalSpeechTextRef.current;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) {
          finalText = `${finalText} ${text}`.trim();
        } else {
          interim = `${interim} ${text}`.trim();
        }
      }

      finalSpeechTextRef.current = finalText;
      setLiveTranscript(`${finalText} ${interim}`.trim());
    };
    recognition.onerror = () => {
      speechRecognitionRunningRef.current = false;
    };
    recognition.onend = () => {
      speechRecognitionRunningRef.current = false;
    };

    speechRecognitionRef.current = recognition;
    try {
      recognition.start();
      speechRecognitionRunningRef.current = true;
    } catch {
      speechRecognitionRunningRef.current = false;
    }
  }, []);

  const sendEndNow = useCallback(() => {
    pendingEndRef.current = false;

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setEndingState("idle");
      setEndError("Not connected. Refresh the page and try again.");
      setAudioPipeline("error", "Not connected. Refresh the page and try again.");
      return;
    }

    try {
      ws.send(JSON.stringify({ type: "end" }));
      setEndingState("ending");
      setAudioPipeline("scoring");
    } catch {
      setEndingState("idle");
      setEndError("Could not send end-interview signal.");
      setAudioPipeline("error", "Could not send end-interview signal.");
    }
  }, [setAudioPipeline]);

  const beginRecordingOnStream = useCallback(
    (stream: MediaStream, stopTracksOnStop: boolean) => {
      recordingStartPendingRef.current = false;

      if (isRecordingRef.current || !connectedRef.current) {
        if (stopTracksOnStop) stream.getTracks().forEach((t) => t.stop());
        if (!connectedRef.current) {
          setAudioPipeline("error", "Not connected. Audio was not sent.");
        }
        if (pendingEndRef.current) sendEndNow();
        return;
      }

      const mime = recorderMime();
      let mr: MediaRecorder;
      try {
        mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      } catch {
        if (stopTracksOnStop) stream.getTracks().forEach((t) => t.stop());
        setAudioPipeline("error", "Could not start the browser audio recorder.");
        if (pendingEndRef.current) sendEndNow();
        return;
      }
      chunksRef.current = [];
      recordingStartedAtRef.current = performance.now();

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onerror = () => {
        setAudioPipeline("error", "Recording failed before audio could be sent.");
      };
      mr.onstop = () => {
        stopLiveTranscription();
        if (stopTracksOnStop) stream.getTracks().forEach((t) => t.stop());

        const blobType = mr.mimeType || mime || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: blobType });
        chunksRef.current = [];
        isRecordingRef.current = false;
        stopRequestedRef.current = false;
        mediaRecorderRef.current = null;
        setIsRecording(false);

        const finishPendingEnd = () => {
          if (pendingEndRef.current) {
            window.setTimeout(sendEndNow, 0);
          }
        };

        if (blob.size < 64) {
          clearLiveTranscriptDraft();
          setAudioPipeline("error", "Recording was too short to process.");
          finishPendingEnd();
          return;
        }

        setAudioPipeline("uploading");
        const reader = new FileReader();
        reader.onloadend = () => {
          const b64 = String(reader.result).split(",")[1];
          if (!b64) {
            setAudioPipeline("error", "Could not encode the recorded audio.");
            finishPendingEnd();
            return;
          }

          const ws = wsRef.current;
          if (!ws || ws.readyState !== WebSocket.OPEN) {
            setAudioPipeline("error", "Not connected. Audio was not sent.");
            finishPendingEnd();
            return;
          }

          try {
            ws.send(JSON.stringify({ type: "audio", data: b64, mime: blobType }));
            setAudioPipeline("transcribing");
          } catch {
            setAudioPipeline("error", "Could not send recorded audio.");
          }
          finishPendingEnd();
        };
        reader.onerror = () => {
          setAudioPipeline("error", "Could not read recorded audio.");
          finishPendingEnd();
        };
        reader.readAsDataURL(blob);
      };

      sendSpeechStart();
      startLiveTranscription();
      try {
        mr.start(250);
        mediaRecorderRef.current = mr;
        isRecordingRef.current = true;
        setIsRecording(true);
        setAudioPipeline("recording");
      } catch {
        stopLiveTranscription();
        if (stopTracksOnStop) stream.getTracks().forEach((t) => t.stop());
        setAudioPipeline("error", "Could not start recording.");
        if (pendingEndRef.current) sendEndNow();
        return;
      }

      if (stopRequestedRef.current) {
        window.setTimeout(() => {
          if (mediaRecorderRef.current === mr && mr.state !== "inactive") {
            try {
              mr.requestData();
            } catch {
              // Some browsers throw if data is not ready yet.
            }
            mr.stop();
          }
        }, 350);
      }
    },
    [
      clearLiveTranscriptDraft,
      sendEndNow,
      sendSpeechStart,
      setAudioPipeline,
      startLiveTranscription,
      stopLiveTranscription,
    ]
  );

  const stopRecording = useCallback(() => {
    if (recordingStartPendingRef.current && !isRecordingRef.current) {
      stopRequestedRef.current = true;
      setAudioPipeline("uploading");
      return;
    }
    if (!isRecordingRef.current) return;
    stopRequestedRef.current = true;
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") {
      try {
        mr.requestData();
      } catch {
        // Data may already have been flushed by a recent timeslice.
      }
      setAudioPipeline("uploading");
      mr.stop();
    }
  }, [setAudioPipeline]);

  const startRecording = useCallback(async () => {
    if (
      isRecordingRef.current ||
      recordingStartPendingRef.current ||
      liveModeRef.current ||
      !connectedRef.current
    ) {
      return;
    }

    recordingStartPendingRef.current = true;
    stopRequestedRef.current = false;
    setAudioPipeline("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      beginRecordingOnStream(stream, true);
    } catch (err) {
      recordingStartPendingRef.current = false;
      stopRequestedRef.current = false;
      setAudioPipeline("error", "Microphone access failed. Check browser permissions.");
      console.error("Mic access denied:", err);
      if (pendingEndRef.current) sendEndNow();
    }
  }, [beginRecordingOnStream, sendEndNow, setAudioPipeline]);

  const stopLiveMic = useCallback(() => {
    liveModeRef.current = false;
    setLiveMode(false);

    if (vadFrameRef.current !== null) {
      cancelAnimationFrame(vadFrameRef.current);
      vadFrameRef.current = null;
    }
    if (isRecordingRef.current || recordingStartPendingRef.current) {
      stopRecording();
    } else {
      abortLiveTranscription();
    }

    liveStreamRef.current?.getTracks().forEach((track) => track.stop());
    liveStreamRef.current = null;
    mediaSourceRef.current?.disconnect();
    mediaSourceRef.current = null;
    analyserRef.current = null;
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
  }, [abortLiveTranscription, stopRecording]);

  const startLiveMic = useCallback(async () => {
    if (liveModeRef.current || !connectedRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioContextCtor();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;

      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);

      liveStreamRef.current = stream;
      audioContextRef.current = ctx;
      analyserRef.current = analyser;
      mediaSourceRef.current = source;
      liveModeRef.current = true;
      setLiveMode(true);
      setAudioPipeline("idle");

      const samples = new Uint8Array(analyser.fftSize);
      const tick = () => {
        if (!liveModeRef.current || !analyserRef.current || !liveStreamRef.current) return;

        analyserRef.current.getByteTimeDomainData(samples);
        let sum = 0;
        for (const value of samples) {
          const centered = (value - 128) / 128;
          sum += centered * centered;
        }
        const rms = Math.sqrt(sum / samples.length);
        const now = performance.now();
        const voiceDetected = rms > 0.035;

        if (voiceDetected) {
          lastSpeechAtRef.current = now;
          if (!isRecordingRef.current && !recordingStartPendingRef.current) {
            beginRecordingOnStream(liveStreamRef.current, false);
          }
        }

        if (
          isRecordingRef.current &&
          now - lastSpeechAtRef.current > 900 &&
          now - recordingStartedAtRef.current > 350
        ) {
          stopRecording();
        }

        vadFrameRef.current = requestAnimationFrame(tick);
      };

      lastSpeechAtRef.current = performance.now();
      vadFrameRef.current = requestAnimationFrame(tick);
    } catch (err) {
      setAudioPipeline("error", "Microphone access failed. Check browser permissions.");
      console.error("Mic access denied:", err);
      stopLiveMic();
    }
  }, [beginRecordingOnStream, setAudioPipeline, stopLiveMic, stopRecording]);

  useEffect(() => () => stopLiveMic(), [stopLiveMic]);

  // Keyboard shortcut: Space
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        startRecording();
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space" && !liveModeRef.current) stopRecording();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => { window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp); };
  }, [startRecording, stopRecording]);

  const sendEndInterview = () => {
    if (endingState !== "idle") return;
    setEndError(null);
    pendingEndRef.current = true;
    stopCurrentAudio();

    const hasActiveCapture =
      isRecordingRef.current || recordingStartPendingRef.current || liveModeRef.current;
    if (isRecordingRef.current || recordingStartPendingRef.current) {
      setEndingState("ending");
      stopRecording();
      if (liveModeRef.current) stopLiveMic();
      window.setTimeout(() => {
        if (
          pendingEndRef.current &&
          !isRecordingRef.current &&
          !recordingStartPendingRef.current
        ) {
          sendEndNow();
        }
      }, 2500);
      return;
    }

    if (hasActiveCapture) {
      stopLiveMic();
    }
    sendEndNow();
  };

  const sendWhiteboardSnapshot = useCallback((snapshot: ArchitectureSnapshot) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "whiteboard", snapshot }));
    }
  }, []);

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
            <ArchitectureCanvas onSnapshotChange={sendWhiteboardSnapshot} />
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
            {messages.length === 0 && !liveTranscript && (
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
            {liveTranscript && (
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-[#3f3f46] bg-[#27272a]/70 px-4 py-2.5 text-sm leading-relaxed text-[#e8e8e8]">
                  {liveTranscript}
                </div>
              </div>
            )}
            <div ref={transcriptEndRef} />
          </div>

          {/* Controls */}
          <div className="shrink-0 border-t border-[#27272a] bg-[#0a0a0b] p-4">
            <div className="flex items-center gap-3">
              {/* Mic button */}
              <button
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture?.(event.pointerId);
                  startRecording();
                }}
                onPointerUp={(event) => {
                  try {
                    event.currentTarget.releasePointerCapture?.(event.pointerId);
                  } catch {
                    // Pointer capture may already be released by the browser.
                  }
                  stopRecording();
                }}
                onPointerCancel={stopRecording}
                onLostPointerCapture={() => {
                  if (!liveModeRef.current) stopRecording();
                }}
                disabled={!connected || liveMode}
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

              <button
                onClick={liveMode ? stopLiveMic : startLiveMic}
                disabled={!connected}
                className={`h-9 rounded-md border px-3 text-xs font-medium transition-colors ${
                  liveMode
                    ? "border-green-400/30 bg-green-400/10 text-green-400"
                    : "border-[#27272a] bg-[#111113] text-[#71717a] hover:border-[#3f3f46] hover:text-[#e8e8e8]"
                } disabled:opacity-40`}
              >
                Live
              </button>

              <div className="flex-1 text-xs text-[#52525b] text-center">
                {liveMode
                  ? isRecording
                    ? "Listening…"
                    : "Live mic on"
                  : isRecording
                  ? "Recording — release to send"
                  : connected
                  ? "Hold mic or Space bar, or use Live"
                  : "Connecting…"}
              </div>
            </div>
            {(audioStatus !== "idle" || audioError) && (
              <div className="mt-3 rounded-md border border-[#27272a] bg-[#111113] px-3 py-2">
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className={audioStatus === "error" ? "text-red-400" : "text-[#a1a1aa]"}>
                    {audioError ?? "Audio"}
                  </span>
                  {audioStatus !== "error" && (
                    <span className="shrink-0 text-[#52525b]">{AUDIO_PIPELINE_LABELS[audioStatus]}</span>
                  )}
                </div>
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-[#27272a]">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      audioStatus === "error" ? "bg-red-400" : "bg-green-400"
                    }`}
                    style={{ width: AUDIO_PIPELINE_PROGRESS[audioStatus] }}
                  />
                </div>
              </div>
            )}
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
