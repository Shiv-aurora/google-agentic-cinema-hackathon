# OSS assessment for Clappy

September 7, 2026. Reviewed the user's recommendation against primary documentation. This is an architecture assessment, not a claim that the integrations have been built or benchmarked.

## Verdict

Reuse established media components so Clappy concentrates on direction, production state, and editable decisions. **Adopt MediaMTX and OpenTimelineIO, keep FFmpeg, and avoid making the entire MediaMTX → OBS → native Swift chain mandatory for the virtual-phone demo.**

The first plan already reused browser recording/WebRTC and FFmpeg rather than implementing codecs. Its unnecessarily custom portion was managing peer-to-peer connections and recording proxies in the director browser. A hub can replace that work. It cannot replace command semantics, synchronization, source verification or editorial judgment.

## Evaluation

| Component | Decision | Analysis |
| --- | --- | --- |
| MediaMTX | Adopt | Independent stream paths, recording and virtual publishers fit the revised demo |
| FFmpeg | Keep | Already available; source simulation, conversion, inspection and rendering |
| OpenTimelineIO | Adopt | Standard edit export and rational timing; retain the application command/event model |
| OBS Studio | Optional | Good for mixed/encoded live output; extra desktop dependency for hosted straight-cut monitoring |
| obs-websocket | With OBS only | Reuse its control interface if adding the adapter; no custom OBS plug-in |
| HaishinKit.swift | Later native iPhone spike | Fits iPhone-only production; no present benefit for virtual sources |
| LiveKit | Strong alternative | SDK-based rooms and connection management; replace MediaMTX if evidence warrants |
| VisionCamera | Defer | No React Native application required for this demo |
| react-native-webrtc | Defer | Adds a mobile stack; sharing capture resources still requires a spike |
| MLT | Defer | Full editing engine exceeds the cut-list-first scope |

## Corrections to the recommendation

### MediaMTX reduces transport work, not all camera engineering

Multiple protocols and a control API are useful building blocks. Our coordinator still owns camera roles, take acknowledgments, and recovery. A hub recording contains what arrived over the network, not necessarily a phone's full-quality original. [Publishing](https://mediamtx.org/docs/features/publish), [control API](https://mediamtx.org/docs/features/control-api)

Segment finalization, incomplete tails and retention need explicit handling. In particular, configure retention to preserve take media rather than inheriting automatic expiry. [Recording](https://mediamtx.org/docs/features/record)

### Protocol conversion is not codec conversion

An SRT source reaching the hub does not establish browser decodability. MediaMTX documents external FFmpeg/GStreamer re-encoding and browser codec constraints. Include preview conversion in the design. [Re-encoding](https://mediamtx.org/docs/features/remuxing-reencoding-compression), [WebRTC compatibility](https://mediamtx.org/docs/features/webrtc-specific-features)

SRT is not a shared capture clock or file-preservation guarantee. For colocated virtual publishers, the simplest tested ingest path wins. A future iPhone transport decision deserves measured SRT/WebRTC comparison.

### OBS can add an unnecessary application dependency

WebSocket control is included in OBS 28 and newer and supports automation. That makes an optional switcher adapter credible. [Official obs-websocket project](https://github.com/obsproject/obs-websocket)

But we still have to supply decodable sources, configure scenes/audio, keep OBS running, and return the program to the product. My engineering judgment is that this is avoidable for the hosted demo: switching among already playing browser views is a small UI operation. It does not require implementing a media mixer. If encoded live compositing becomes necessary, use OBS rather than build that ourselves.

### OTIO is not a renderer or agent protocol

OTIO describes editorial data and references external media. It does not replace roll/cut acknowledgments or automatically translate a timeline into an FFmpeg operation. [Official overview](https://opentimelineio.readthedocs.io/en/latest/)

Construct OTIO at one validated cut-list boundary and compile its supported subset. Derive the UI and exported timeline from that same immutable version.

### Swift is a sensible native direction, not today's fastest proof

HaishinKit lists RTMP/SRT and explicit Xcode/Swift requirements. That supports later native evaluation. [HaishinKit](https://github.com/HaishinKit/HaishinKit.swift)

For virtual phones, native setup and simultaneous local-recording/streaming work delay the demonstrated functionality. Keep a camera adapter seam; drawing an iPhone frame around a web video does not prove native capture.

### LiveKit is not tied to React Native

LiveKit also provides web and native Swift SDKs. Its transport handles connection/subscription concerns, while recording/export has its own service deployment. [Transport](https://docs.livekit.io/transport/), [egress](https://docs.livekit.io/transport/self-hosting/egress/)

It is a valid iPhone architecture. MediaMTX wins this particular choice because routed file publishers and hub recording fit the revised demo. This is a scope-based decision, not a general filmmaking ranking. If LiveKit is used, choose its transport SDKs and retain Google ADK for AI.

## Practical change

Replace bespoke media signaling and browser proxy recording with one MediaMTX service. Add three FFmpeg-backed virtual camera adapters and promote OTIO to the first editing milestone. Keep OBS and native capture outside the demo's required path. Preserve synchronization, originals, Google AI, ClickHouse MCP, voice direction and alternate edits as core requirements.

No star counts were used as evidence. Pin versions, preserve notices, and inspect actual licenses before distribution. Do not import every suggested repository because it is mature.

The first integration gate is three publishers → hub → browser → independent recordings → frame-correct OTIO/MP4. This will establish whether the selected combination reduces actual implementation work.
