# Clappy virtual-camera demo

Recorded example: `output/playwright/clappy-final-walkthrough.mp4` (169.28 seconds,
silent actual hosted UI, no accelerated waits). The original WebM is retained.
It demonstrates manual roll, live Google direction, manual hold, CUT, a real
alternate and A/B review; synthetic browser voice is verified separately.

## Open the actual app

Use https://35-254-38-201.sslip.io, not the raw player HTML file. The private
invitation is in local `data/hosting-access.json`; do not put it in a recording or
public URL. A browser keeps its production key locally. Keep that browser's
storage to return to its takes. The one-VM demo supports one active rig at a time.

The host automatically stops after 24 hours of runtime. A stopped host is not
proof that saved takes were deleted. Follow `HOSTING.md` for recovery; restarting
can change its ephemeral IP. Disk storage remains billable after STOP.

## Demonstrate the real loop

1. Scene settings: select the live-action café rehearsal and inspect the six-line scene.
   Explain that the three virtual iPhones are derived views of an original
   Google-generated still, with synthesized dialogue—not physical cameras.
2. Enable AI director, then Arm cameras. Speak a direction → “Roll cameras” →
   Send direction, or use the manual Roll cameras control. A real microphone
   requires browser permission. Synthetic-input test evidence is separate.
3. Keep the program monitor visible for about 25–35 seconds. The real source
   audio is transcribed by Google; Google shot proposals consult actual scoped
   ClickHouse memory. The first cold proposal may be rejected as stale. Later
   valid proposals can change the view. Never claim every proposal will apply.
4. Click Bella and Hold shot to show director precedence. Release hold to return
   control, or press Cut. CUT does not depend on model inference or remaining AI
   allowance. The 50-second take limit is a final safety stop.
5. Wait for the original MP4 to finish rendering. Play it and inspect the
   timeline, camera percentages, recording verification and explicit estimated
   live-timing label.
6. Request: “Create a new edit using one continuous shot of camera b, Bella,
   for 100% of this take. Preserve the full duration and original edit.” Wait for
   the real Google/MCP result and renderer; do not replace an error with a
   staged success. Other editorial requests are supported but can be rejected
   if generated frame coverage or allocations are invalid.
7. Switch between the live cut and alternate. The playhead and playback state
   should persist. Download MP4, OTIO timeline and Source evidence. The original
   edit and immutable source generations remain available.

## Explain the scope honestly

- Runtime AI: Google Cloud Speech, Gemini/Google ADK, with official ClickHouse
  MCP memory. Live choices have a mandatory MCP preflight; full alternate edits
  use the ADK tool loop. Codex is the development tool, not the app's AI engine.
- Transport and recordings are real MediaMTX/FFmpeg media. Final edits are
  validated OTIO/FFmpeg renders from preserved synthetic originals.
- Chrome and WebKit/iPhone-sized browser checks are not native iPhone or Apple
  Simulator tests. No lip-sync or independent live-action angle claim.
- Source-frame identity and receive-clock evidence are recorded. Live-edit
  timing still uses an explicitly labeled publisher-clock estimate. There is no
  claim of frame-locked live display or physical multicamera synchronization.
- This deployment has invitation/usage controls, not production-scale account
  management or a guaranteed dollar spending cap.

## Failure and restart behavior

If the browser disconnects, reload the same origin with its local storage intact.
Do not create another production to bypass usage caps. A lost selected camera
falls back to healthy coverage; loss of all cameras stops with partial coverage.
Coordinator restart marks unfinished takes interrupted and preserves saved
media/edits. A failed alternate does not destroy its original.

Do not run the installer or restart the coordinator during a take or render.
Use the scoped service-status and health commands in `HOSTING.md`. Preserve
`data/`, database volumes and usage/egress ledgers across updates. Do not publish
credentials in logs, source archives or walkthrough footage.

## Recheck before sharing

`npm run build` and `.venv/bin/python -m pytest -q` are local, non-Google checks.
The media/MCP and hosted evidence scripts are listed in README. Voice, live
direction and alternate-edit smokes make real Google calls and consume the
configured allowances. Read `BUILD_STATUS.md` for the exact evidence and limits.
