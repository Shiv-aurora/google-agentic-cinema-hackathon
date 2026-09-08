# Clappy

Your little film crew: a Google-powered director for multicamera production.

**In development.** This demo uses three labeled virtual iPhones and owned synthetic footage, including a cinematic still-frame animatic with Google voices. It transports/records actual media, renders OTIO edits, follows dialogue through actual Google transcription, and uses Google ADK + official ClickHouse MCP for direction. A protected Google Cloud deployment is now running; exact live-cut synchronization and final acceptance remain in progress. See [build evidence](docs/BUILD_STATUS.md) and [implementation plan](IMPLEMENTATION_PLAN.md).

## Hosted demo

[Open Clappy](https://35-254-38-201.sslip.io). An invitation is required. The deployment has a 24-hour automatic VM stop, conservative operation allowances and an egress circuit breaker; the persistent disk remains billable after STOP. See [hosting and recovery](docs/HOSTING.md). Never use the raw `apps/player/index.html` file as the app: it is an authenticated player template, not the studio entry point.

Follow the [demo runbook](docs/DEMO_RUNBOOK.md) for the complete camera → Google direction → preserved original → alternate-edit loop. [Attribution and source provenance](docs/THIRD_PARTY_NOTICES.md) document the OSS foundation and synthetic-media scope.

## Run locally

Prerequisites: Node/npm, Python 3.12+, `uv`, Docker, FFmpeg/ffprobe, Chrome. Google features require an authorized Google Cloud identity and enabled/billed Vertex AI project. No non-Google model API powers the app.

```sh
npm ci
uv sync --locked
uv sync --locked --project infra/mcp-clickhouse
.venv/bin/python -m scripts.configure_media_auth
docker compose -f infra/compose.yaml up -d
.venv/bin/python scripts/generate_fixtures.py
```

Start the API and web app in separate terminals:

```sh
CLAPPY_AUTH_MODE=gcloud .venv/bin/uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

```sh
npm run dev
```

Open `http://localhost:5173`. Arm → roll → select cameras → cut → review. Ask Clappy about this production or request another edit. Errors are displayed, never replaced with canned AI results. Current fixture takes automatically stop after 50 seconds.

The first ARM prepares versioned rehearsal sources with a visible frame-code strip; this may take longer than subsequent arms. Parent originals and old takes are preserved. New source-evidence exports include decoded browser frame IDs and receive-clock fits with explicit uncertainty. These do not yet retime the live edit. See [source-clock measurement and preparation](docs/SOURCE_CLOCK.md).

For the Google-voiced rehearsal, enable the project's Text-to-Speech and Speech-to-Text APIs, then generate owned sources:

```sh
CLAPPY_AUTH_MODE=gcloud .venv/bin/python -m scripts.generate_scene_audio
.venv/bin/python -m scripts.generate_scene_sources
CLAPPY_AUTH_MODE=gcloud .venv/bin/python -m scripts.generate_voice_fixtures
```

Choose the dialogue source in Scene settings, enable the AI director, arm and roll. Camera C's actual audio drives Google recognition. “Speak a direction” captures the separate director microphone; tap “Send direction” when finished. It requires localhost/HTTPS and microphone permission. User voice is sent to Google for recognition; the microphone is not left running.

For cinematic visuals, generate a Google still plate and render its three derived views (paid Google generation; existing assets are reused):

```sh
CLAPPY_AUTH_MODE=gcloud .venv/bin/python -m scripts.generate_scene_visual
.venv/bin/python -m scripts.generate_animatic
```

Select “cinematic animatic (derived views)” in Scene settings. These are crops of one generated still with camera motion and synthesized dialogue—not independent live-action angles or lip-synced video. Provenance and disclosure accompany the media. Use the monitor's sound button to enable one continuous master feed; all other players stay muted. A/B review keeps your playhead and playback state when changing versions.

The development project defaults explicitly to `clappy-cinema-2026-0907`; override `CLAPPY_GOOGLE_PROJECT` for your own project. `CLAPPY_AUTH_MODE=gcloud` refreshes tokens through the already signed-in CLI without writing/logging them. Omit that setting to use standard ADC (required for deployment). `.env.example` documents settings; export them or pass `--env-file .env` to uvicorn.

The local MediaMTX and ClickHouse ports bind only to loopback. The media bootstrap creates a private admin key and hashed configuration; each take gets separate per-camera publisher/reader accounts, revoked at CUT. See [media access and lifecycle limitations](docs/MEDIA_ACCESS.md). The included ClickHouse password is **local development only**. Hosting uses the separate `infra/hosting` configuration with generated secrets, HTTPS, deliberate WebRTC transport exposure and perimeter limits.

Optional invite admission and persistent app usage limits are now available. See [access and limits](docs/ACCESS_AND_LIMITS.md) and `.env.example`. These controls do not replace media authentication or create a dollar spending cap. Keep `data/usage.sqlite` when preserving or moving the demo.

## Verification

```sh
npm run build
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.smoke_media
.venv/bin/python -m scripts.smoke_memory
CLAPPY_AUTH_MODE=gcloud .venv/bin/python -m scripts.smoke_director
CLAPPY_AUTH_MODE=gcloud .venv/bin/python -m scripts.smoke_speech
.venv/bin/python -m scripts.smoke_live_director
.venv/bin/python -m scripts.smoke_voice
.venv/bin/python -m scripts.smoke_queued_voice
.venv/bin/python -m scripts.smoke_camera_failure
.venv/bin/python -m scripts.smoke_access
.venv/bin/python -m scripts.smoke_media_auth
npx playwright test
```

For the real paid Gemini browser edit test, run `CLAPPY_TEST_AI=1 npx playwright test` with the API using authorized Google credentials. Run media tests sequentially: this demo rig allows one active take.

Use `CLAPPY_TEST_VOICE=1 npx playwright test tests/e2e/voice.spec.ts` to test browser MediaRecorder with an explicitly synthetic microphone source (not a physical-device claim).

The camera-failure smoke deliberately kills only its own test-take publisher, then verifies safety fallback and partial coverage. It preserves media. For WebKit/iPhone browser emulation, install `npx playwright install webkit`, then run `npx playwright test -c playwright.webkit.config.ts`. This is not physical-device testing.

Add `--all-cameras` to the failure smoke to verify automatic stop when the entire rig disappears. New renders also verify actual recorded frames against immutable originals and offer a `Source evidence` JSON download. [Media verification scope](docs/MEDIA_VERIFICATION.md) explains why this does not yet prove frame-accurate live-cut synchronization.

Generated outputs are ignored under `data/` and `artifacts/`. Preserve fixtures, recordings, edits and `data/clappy.sqlite` to keep takes. `docker compose -f infra/compose.yaml stop` stops services without deleting media or database volumes.

## Architecture

React/Vite → FastAPI/SQLite coordinator → MediaMTX/FFmpeg cameras → OTIO/FFmpeg renders. Transactional events feed ClickHouse; each production's ADK agent uses the official MCP server with a server-enforced read-only view. ADK and MCP run in separate locked Python environments. See [OSS assessment](docs/OSS_ASSESSMENT.md).

Live direction performs a mandatory official-MCP history read before a single Google shot-selection call. Full alternate edits and recall use the ADK tool loop. Raw frame/clock evidence stays in the audit store and is excluded from the creative recall view; take context is bounded independently. Hosted live choices use `gemini-2.5-flash-lite`; edits use `gemini-2.5-flash`. A model/tool failure never becomes a canned shot or a fabricated successful edit.
