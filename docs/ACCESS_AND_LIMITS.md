# Demo admission and usage limits

These controls are implemented and locally tested. Scoped MediaMTX read/publish authentication is also now implemented; see [media access](MEDIA_ACCESS.md). The complete stack is not ready for public deployment: public TLS/WebRTC routing, request/connection limits and hosted verification are still outstanding.

## Invitation and production identity

Set `CLAPPY_DEMO_ACCESS_KEY` to a randomly generated secret of at least 32 characters to require an invitation before creating a production. Never use a `VITE_` variable, commit the secret, place it in a URL, or reuse the local browser-test fixture code. Empty/unset keeps the local development entry open.

The UI sends an invitation once in the `X-Clappy-Invite` header. It clears the field after success and does not persist the invitation in localStorage. The returned random production key is stored on that browser and remains scoped to one production. An invitation does not grant access to someone else's existing production. Rotating it blocks future admission using the old code; it does not revoke already issued production keys.

For hosting, `CLAPPY_PUBLIC_ORIGIN` must be the exact HTTPS origin, without a route or query. Startup rejects malformed origins, short invitation secrets, and a public origin without an invitation. Browser HTTP and WebSocket origins are checked. Requests without an Origin header still need the appropriate invitation or production key. API responses are marked `no-store` and `nosniff`; hosted production cookies are Secure, HttpOnly and SameSite Strict.

This is a shared invitation gate for a bounded demo, not per-person account management. Do not publish the demo publicly until the remaining media and perimeter controls are verified.

## Persistent admission budgets

`data/usage.sqlite` stores atomic reservations per UTC day. Preserve this file during deployment, backups and restarts; deleting it resets the ledger. Defaults can be reduced through environment variables before a public demo:

| Variable | Default daily allowance | What is reserved |
| --- | ---: | --- |
| `CLAPPY_DAILY_SESSIONS` | 100 | One per newly created production |
| `CLAPPY_DAILY_TAKES` | 60 | One before starting a take |
| `CLAPPY_DAILY_RENDERS` | 100 | One at roll for its live edit; one per requested alternate |
| `CLAPPY_DAILY_AI_JOBS` | 200 | One per director job; one conservatively reserved per voice interpretation |
| `CLAPPY_DAILY_SPEECH_SECONDS` | 3600 | 60 seconds before a dialogue take; 12 per director-audio upload |
| `CLAPPY_DAILY_VOICE_REQUESTS` | 100 | One before processing director audio |

A zero allowance disables admission for that category. Multi-category reservations are all-or-nothing. An identical operation ID is idempotent, and concurrent database handles cannot overspend the allowance. Failed/abandoned jobs are not refunded: this deliberately avoids free retries of potentially billable work. A new UTC day gets a new bucket.

These are **operation caps, not dollar caps**. A director job can make multiple bounded model/tool turns and SDK retries. They do not cover VM/disk/network charges, development-time media generation scripts, or commands run outside the application. Set cloud budgets/alerts and service quotas separately, inspect actual billing, and retain a controlled demo window. No dollar guarantee is implied.

Manual CUT, camera selection, hold/release, review and existing downloads do not reserve paid work. In particular, a take whose allowance has been consumed can still be cut. Exhaustion rejects new work with visible feedback; it does not replace Google output with a canned response.

An authenticated director can inspect `/api/sessions/{session_id}/limits` for remaining app-wide allowances. Media alignment and rendering run with one CPU-heavy job at a time. Remaining production safeguards include per-connection/request limits, tighter hosted configuration, crash-time media credential cleanup and external tests.

## Verification

```sh
.venv/bin/python -m pytest tests/integration/test_usage.py -q
.venv/bin/python -m scripts.smoke_access
```

The smoke starts its own temporary loopback API and database, with AI/voice budgets set to zero. It checks invitation rejection, cross-production denial, HTTP/WebSocket foreign-origin rejection, session exhaustion, AI/voice admission denial, CUT after quota exhaustion and rejection of another roll. It makes no Google AI call. Its disposable camera take uses the normal local media hub; run it sequentially with other media tests. Generated hub recordings are preserved.

Evidence: `artifacts/access-smoke.json`. Browser checks separately confirmed wrong-code rejection, successful admission, no invitation persistence, and preservation of the same production across an API outage/retry. The temporary local test invitation is removed after verification.
