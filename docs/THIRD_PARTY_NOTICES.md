# Third-party components and media provenance

Clappy builds on existing software; it does not claim authorship of its media server,
codecs, timeline interchange, SDKs or database. Dependency versions are recorded in
`package-lock.json`, both `uv.lock` files, and pinned container digests in
`infra/hosting/compose.yaml`.

## Attribution inventory

Run `.venv/bin/python -m scripts.collect_notices` after installing the locked
environments. `artifacts/notices/inventory.json` records installed Python/npm
versions and declared licenses; adjacent files preserve the supplied license and
notice texts verbatim. Missing metadata is left missing, not assigned a guessed
license. This inventory is not a complete distribution-compliance audit.

Major building blocks are React, Vite, Lucide, FastAPI, Pydantic, Google ADK,
Google Gen AI SDK, Google Cloud Speech/Text-to-Speech SDKs, OpenTimelineIO,
ClickHouse Connect, and the official `mcp-clickhouse` server. The player loads
MediaMTX's WebRTC reader from the installed MediaMTX service.

MediaMTX and ClickHouse run as separate pinned containers. FFmpeg/ffprobe, nginx,
Python and other host packages retain the notices supplied with their installed
distributions. FFmpeg licensing depends on its build configuration and enabled
components; do not describe every build as having the same license. Before
redistributing binaries/container images, collect their exact notices and any
required corresponding-source materials. No app-source license is granted merely
by installing or documenting these dependencies.

## Original synthetic media

`assets/demo/last-train-v1/provenance.json` records the Google model, generation
prompt, creation time and SHA-256 of the original scene plate. The characters and
dialogue are fictional. Camera A/B/C animatic files are derived crops/motion of
that one still, accompanied by Google-synthesized dialogue. They are not three
independent live-action angles, lip-synced performances or physical iPhone footage.
Source-generation manifests retain hashes and lineage; frame-coded derivatives
do not overwrite their parents.

The browser test microphone uses an owned Google-voiced WAV fixture. It is not a
recording of the user's microphone. No non-Google model API powers this app.

Do not publish `data/`, environment files, production/browser keys, cloud access
details or database volumes as part of an open-source source archive.
