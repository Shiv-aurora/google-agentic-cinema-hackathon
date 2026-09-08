# Local media access and lifecycle

Implemented and locally verified; this is not a public-deployment sign-off.

## Bootstrap

Run `.venv/bin/python -m scripts.configure_media_auth` before starting Compose. It creates `data/media-admin.key` and `data/mediamtx-secure.json`, both mode 0600. Preserve the key privately and never commit either file. An identical bootstrap leaves the configuration contents unchanged. A changed template can reload the hub: apply configuration changes only while the rig is idle.

Compose mounts the generated configuration into the pinned MediaMTX container. The checked-in YAML is a template with no anonymous users. The administrator has only control-API permission, not media read/publish permission. The API reads the private key through `CLAPPY_MEDIA_ADMIN_KEY_PATH`; browser code never receives it.

## Take credentials

Before starting publishers, the coordinator adds six native MediaMTX accounts: one publisher and one reader for each of cameras A, B and C. Each account has exactly one action and one take/camera path. Passwords are random; the hub configuration receives SHA-256 hashes. The scheme uses [MediaMTX's built-in authentication](https://mediamtx.org/docs/features/authentication), not a custom token verifier.

The production-authenticated player requests its camera credential from the API. The browser sends it to WHEP using the pinned MediaMTX reader SDK. Credentials are not embedded in player URLs, HTML, session state or event exports. They remain accessible to the authorized browser while the take is live; this is scoped access, not DRM. Responses are no-store and the player has a restrictive content security policy.

FFmpeg uses temporary scoped credentials in local RTSP process arguments. Publisher stderr is redacted before writing logs; the transcription reader discards stderr. A privileged local user can inspect process arguments, so the host remains a trust boundary. Do not expose process listings, diagnostics or raw credential responses in demo recordings.

CUT stops publishers and removes the six accounts. Live ticket requests then fail. Credential removal is also attempted on startup failure and normal coordinator shutdown. Failed removal remains queued in memory for another stop/close attempt.

## Operational constraints

- Run only one coordinator against this media hub. Configuration updates are serialized in-process, not across processes.
- MediaMTX's config GET masks passwords. The coordinator reconstructs known hashes rather than writing those masks back. Unexpected non-Clappy users cause refusal, not silent overwrite.
- After an ungraceful restart, stale Clappy accounts are removed on the next account update only if no media paths are ready. Active unknown ownership causes refusal. There is no durable revocation journal or guaranteed immediate crash-time revocation yet.
- Keep all direct media/control ports loopback-bound. Hosted delivery still needs HTTPS, deliberately exposed WebRTC transport, private control/publish endpoints, request and connection limits, storage bounds and external verification.
- Authentication removal prevents new authorized connections; the local CUT test also ends publishers. No claim is made here about forcibly terminating arbitrary pre-existing remote readers without stopping their publisher.

## Evidence

`artifacts/media-auth-smoke.json` records passing scoped access and post-CUT revocation checks without secrets. The Python regression suite includes exact path/role permissions and masked-config preservation. Chrome and WebKit playback passed with the authenticated wrapper. The subsequent real Google live-director test recognized six lines and applied four memory-backed decisions over a 38.2-second take, including manual hold/release.

Run media regressions sequentially because they share one local rig. Existing recordings and source files are preserved.
