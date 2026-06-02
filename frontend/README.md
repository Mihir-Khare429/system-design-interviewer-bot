# System Design Interviewer Frontend

Next.js browser app for the System Design Interviewer. It provides auth, problem selection, the interview room, React Flow whiteboard, real-time audio controls, live transcript, and scorecard UI.

The FastAPI backend must be running separately on `http://localhost:8000`.

## Run Locally

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

Required local setting:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Key Screens

- `/` — landing page
- `/auth/signin` and `/auth/signup` — JWT-backed auth through the FastAPI API
- `/dashboard` — previous interview runs and plan status
- `/problems` — problem catalog and filters
- `/problems/[slug]` — problem details and difficulty picker
- `/interview/[sessionId]` — live interview room

## Interview Room

The interview room uses one WebSocket connection to `/ws/interview`.

Client sends:

- `speech_start` when the user starts speaking, so Alex can stop current playback
- `audio` with base64 WebM and MIME type after each recording
- `whiteboard` snapshots from the React Flow canvas
- `end` when the user ends the interview

Server sends:

- `session_started`
- `audio_received`
- `processing_state` for `transcribing`, `thinking`, `speaking`, `scoring`, `idle`, and `error`
- `transcript`
- `response` and `response_audio`
- `interrupt`
- `phase_change`
- `scorecard_loading` and `scorecard`

The UI shows a compact audio pipeline bar so recording, upload, transcription, thinking, speaking, scoring, and error states are visible instead of silent.

## Audio Behavior

- Push-to-talk: hold the mic button or Space bar.
- Live mode: voice activity detection starts/stops recordings automatically.
- Browser speech recognition shows a live local transcript draft while the user is speaking.
- Whisper transcript from the backend becomes the final user message.
- Barge-in stops Alex's current audio when the candidate starts speaking.
- End interview waits for an active recording to upload before sending `end`.

## Common Commands

```bash
npm run dev      # start local dev server
npm run build    # production build and type check
npm run start    # serve production build
npm run lint     # eslint
```

If Next reports a missing chunk such as `Cannot find module './948.js'`, stop the dev server, delete `.next`, and restart:

```bash
rm -rf .next
npm run dev
```

## Source Map

```text
src/app/                         App Router pages
src/components/interview/         Interview session and whiteboard
src/components/layout/            Navbar and layout chrome
src/components/billing/           Billing/upgrade controls
src/lib/api.ts                    FastAPI REST client and token helpers
src/lib/auth-context.tsx          Auth provider
src/lib/problems.ts               Local problem catalog
```
