# Source-frame and receive-clock calibration

This is implemented measurement for the owned virtual-camera adapter. It is **not** a certification of physical capture time, frame-locked display, or exact live-edit timing. Existing live edits still use their explicit publisher-clock estimates; they are not silently retimed.

## Versioned source references

ARM prepares a new immutable source generation under `data/framecoded/`. The destination includes the parent manifest hash and code version. Parent originals are never overwritten. Each take stores its own source directory; old takes without that field keep their previous sources. Switching the source set after arming requires re-arming.

Each 960×540 frame carries a 352×12 pixel strip, eight pixels from the lower/right edges. It encodes a version marker, short source-generation tag, camera, zero-based frame number and CRC16. The full source hashes remain in the manifest: the short tag and CRC are identification/error-detection aids, not cryptographic authentication. All 16,200 frames in the nine prepared 60-second rehearsal files were decoded after encoding and checked for the expected camera, tag, sequence and checksum.

FFmpeg overlays the strip and copies the existing audio. The coded derivatives are the new take's preserved source references for both publishing and conforming. The stream recorder's decoded SHA-256 verification therefore still compares like-for-like video, rather than comparing a coded derivative to an uncoded parent. [FFmpeg overlay documentation](https://ffmpeg.org/ffmpeg-filters.html#overlay)

Prepare ahead of time to avoid first-ARM encoding latency:

```sh
.venv/bin/python -m scripts.prepare_framecodes data/fixtures
.venv/bin/python -m scripts.prepare_framecodes data/scenes/last-train-v1
.venv/bin/python -m scripts.prepare_framecodes data/scenes/last-train-animatic-v1
.venv/bin/python -m scripts.prepare_framecodes data/scenes/open-cafe-v1
```

Preparation is serialized by the API. Existing verified generations are reused, with file hashes checked. Sources must be zero-based, 960×540, 30 fps files with the expected frame count. Other source formats are rejected, not implicitly assigned an invented timecode.

## What the browser measures

Once per second, a visible browser reads the small code region from each progressing program subscription using a canvas. Invalid/low-contrast checksums are omitted. The server validates each decoded packet against the take's source tag, camera and frame-count bounds. WebKit can report zero browser media timestamps; the pixel code provides the independent source-frame number. [Canvas pixel-read API](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/getImageData)

Displayed-cut acknowledgments also decode the selected source during the compositor callback. They retain decision acceptance, browser metadata, decoded source identity and server receipt separately. A pixel read during that callback does not certify the exact physical display instant.

Receivers are grouped by browser, camera and locally assigned track-object epoch. MediaMTX's generic stream name is not treated as a unique receiver identity. Samples across different receiver epochs are never silently merged.

## Clock bounds and fitting

An authenticated clock probe records server receive/send times. The browser returns its own send/receive times. For server-minus-browser clock offset, the feasible interval is:

`[server_send − client_receive, server_receive − client_send]`

This does not assume symmetric network delay. Exchanges over two seconds are rejected. Pixel-read brackets must be no more than 100 ms wide and no more than 12 seconds after the probe; the server expires probes after 15 seconds. A stated 200 ppm clock-rate allowance widens the interval over that short lifetime. This allowance is an assumption, not a measurement of arbitrary phone clocks.

Each take retains raw requests, server probes and derived session-time intervals. Per-receiver fits use `session_time = offset_seconds + scale × source_seconds`. At least six samples spanning four source seconds are required. Backward source motion, scale outside 0.98–1.02, or observed uncertainty above 150 ms prevents a passing fit. The reported envelope includes the largest residual, clock-interval half-width and one source frame of quantization. Outliers are not silently removed. This is an empirical bound over the recorded sample range, **not a guarantee for future or extrapolated times**.

Sampling is bounded to three strips per batch, one batch per second per view, 180 accepted batches per take and 24 cached probes. Requests have five-second client timeouts. The sampler is torn down when leaving the live view/take; hidden browser documents do not sample. Manual CUT does not wait for calibration to pass.

## Current evidence

- Python/JavaScript packet parity, all single-bit corruptions, ambiguous pixels, asymmetric clock bounds, source binding, expiry, known offsets, drift and frozen-frame fits have unit coverage.
- Chrome take `6fd27af086624e329083683ebd7a4f96`: 48 live batches over a 50-second take. B/C fits passed at approximately 139/136 ms observed uncertainty; A was rejected at approximately 183 ms. This rejection is retained, not relabeled as synchronized.
- WebKit take `8caff6d3c43143e892334617b9373127`: 14 live batches from all three cameras. The opening C acknowledgment decoded source frame 90; the manual A cut decoded frame 240, both with browser media PTS zero. Per-receiver observed fit envelopes were approximately 44–74 ms over their sampled ranges. The take's recordings verified and MP4 rendered; its exported source manifest retains all batches and fits.
- Screenshot: `output/playwright/framecode-webkit-live.png`. Earlier originals, recordings and edits remain available.

## Gates still open

Inject delayed publishers and receiver restarts; verify clock-epoch recovery and fits under those conditions. Tie the accepted decision versus displayed source-frame evidence to an explicit conforming policy, including the unobserved opening interval and continuous master audio. Verify any resulting retiming in rendered frames before changing the live-edit label. Native iPhone/wireless capture clocks and physical-device synchronization are outside the virtual-demo evidence.
