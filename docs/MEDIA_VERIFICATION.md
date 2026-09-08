# Media identity and timing evidence

Clappy's virtual publishers copy H.264 video into MediaMTX. The review worker compares decoded SHA-256 frame hashes of each recorded segment against the preserved source. FFmpeg provides the per-frame hash output; timestamps are evaluated separately from hash identity. [FFmpeg framehash documentation](https://ffmpeg.org/ffmpeg-formats.html#framehash)

## What is verified

- The current source file matches its immutable manifest hash.
- Unique frame anchors identify the exact starting source frame of a received segment.
- Every decoded frame agrees with that mapping. A missing, duplicated, reordered, unmatched or ambiguous sequence cannot pass.
- Media timestamps follow the expected 30 fps cadence within one frame.
- Consecutive recorded segments have contiguous source-frame ranges.
- The recordings cover the source-frame interval requested by the edit.
- A camera that was observed offline still has partial coverage, even if its remaining fragments decode.

The matcher fails closed for re-encoded video and insufficiently distinctive footage. This method is for the current copy-video virtual adapter, not a general camera synchronization algorithm.

## What is not yet proven

Exact source-frame identity does **not** measure the source frame visible when a director's live command was accepted. The coordinator still uses publisher-clock estimates for that session-time origin. Browser playback is not frame-locked. Native phone clocks, wireless latency and physical capture are not tested.

Accordingly the review label says “Source frames verified · live timing estimated.” Do not shorten that to “frame-accurate synchronization.” The next timing gate is a measured session-time/source-time transform under delayed publishers and drift. Client composition observations are now implemented as a separate prerequisite, not a substitute for that transform.

## Browser composition observations

New frame-coded takes additionally identify source pixels and bracket browser/server clocks. See [source-clock measurement](SOURCE_CLOCK.md) for its evidence, limits and the still-open conforming gate.

Each new take gets a clock epoch. The authenticated monitor endpoint records the browser ID, player epoch, accepted decision's camera/time, frame metadata, browser-local observation time and server receipt time relative to ROLL. Reports are bounded to 240 per take and deduplicated by ID. Inactive takes, old epochs and nonexistent decisions are rejected. A late observation can be retained as historical evidence but cannot change a newer decision.

The UI uses `requestVideoFrameCallback` to observe composition. This API is best effort, not a guarantee of exact physical display timing. Its media timestamp belongs to the browser's playback timeline; it is not assumed to be the original source timestamp. [Browser API semantics](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback)

WebKit verification returned zero media timestamps while video advanced. Health therefore uses increasing compositor-frame counts. No synthetic timestamp is substituted. Browser and server monotonic clocks also remain separate: the difference between server receipt and decision acceptance includes observation/delivery delay, not a measured one-way network latency.

After 2.5 seconds without an advancing composed frame, a visible director view reports a stall. Initial connection gets a separate 10-second grace period; a paused or ended player does not count as healthy even if callbacks arrive. It requests fallback only when another actual program subscription has advancing playback and the server still considers that camera available. The server rechecks the latest camera decision, records an explicit `monitor-fallback` cut and clears a hold on the stalled view. Original publishers and recordings continue. Phone-card previews are not used as proof that a different program subscription is healthy.

Observers stop when leaving the live view or take. Hidden documents and off-screen monitors suspend stall checks. Unsupported browsers show an unavailable status instead of inventing acknowledgments. A failed evidence upload is visible; automatic network retry, reconnect/frame-counter resets and full background-tab/multiple-director behavior still need further verification. This detects non-progressing playback, not repeated imagery inside an otherwise advancing stream.

The source-evidence manifest includes these observations separately from recorded-frame alignment. They do not change source offsets or silently retime the original edit. The compositor callback on the newly selected camera is observed separately from accepting its fallback cut.

Chrome browser-only pause evidence: production `8e630561419e458ebc1f3b9d199bbc5b`, take `2883f6eb85ca4b17acbcb506dafe10fe`. A C-player stall was reported after 2745 ms, the coordinator cut to A at 27.033 seconds, and A's composition report arrived at 27.090 seconds. All three publishers remained RECORDING. The take auto-stopped at 50 seconds, all recordings verified, and its MP4/source manifest completed. These are observation/receipt times, not an exact command-to-photon measurement.

Clean WebKit CLI verification: production `e9b8acf45990476083a65be6fa3fee5c`, take `ebc4340a21be45eb9b73e91a81ad8ad0`. Five seconds of healthy visible playback produced no stall; explicitly pausing C triggered a report after 2513 ms and a cut to A at 10.1 seconds. A composition acknowledgment arrived at take-relative 10.111 seconds. All publishers remained RECORDING. The test checked the server's actual decision list, captured `output/playwright/webkit-monitor-fallback-verified.png`, and issued CUT. Earlier diagnostic takes are preserved but are not passing fallback evidence.

This verification also found duplicate React roots after development hot reload. The entry point now reuses its development root; frame observers, intervals and pending uploads clean up when their component/take changes. Final WebKit verification used a clean page reload.

## Evidence and reproducibility

```sh
.venv/bin/python -m pytest tests/integration/test_alignment.py -q
.venv/bin/python -m scripts.smoke_media
.venv/bin/python -m scripts.smoke_camera_failure
.venv/bin/python -m scripts.smoke_camera_failure --all-cameras
```

Run media tests sequentially against the local API and MediaMTX. Crash tests target only their own unique take/publisher processes and preserve files. No Google AI call is needed for these tests.

Unit checks recover a known three-second remux offset to one output frame and reject missing frames, drift, ambiguous content and missing opening coverage. The actual cinematic take `deae926e2f114b8a966b62295be88546` had 963 matching frames per camera, across four contiguous segments each, with zero media-clock residual in the inspected files. This is a recorded-media result, not a live-cut clock measurement.

New review renders expose a session-authenticated `Source evidence` JSON download. It contains source and recording hashes, matched frame ranges, coverage, parent edit identity, OTIO hash and final MP4 hash. The source originals and parent edits are unchanged. Background verification/rendering is limited to one CPU-heavy job at a time; CUT itself does not wait for all frame hashes.

Per-take reports live under `data/alignment/`; per-edit export manifests live under `data/manifests/`. Browser and HTTP smoke evidence is under `artifacts/`. These generated directories are ignored; preserve them along with the database and sources when moving the demo.
