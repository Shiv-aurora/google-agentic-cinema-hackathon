# Hosted Clappy demo

The user approved hosting up to $25 against the linked Google Cloud billing account, then explicitly instructed development to proceed without further credit checks. Credit eligibility is not independently certified here.

## Dedicated resources

- Project: `clappy-cinema-2026-0907` (all commands must select it explicitly).
- VM: `clappy-demo-1`, `us-central1-a`, `e2-standard-4`, Ubuntu 24.04, 30 GB standard persistent boot disk.
- Site: https://34-133-211-128.sslip.io — free DNS based on the current ephemeral IP; a stopped/restarted VM may receive a different address, requiring DNS/config/certificate updates.
- Isolated `clappy-demo` network and `clappy-demo-central` subnet. SSH only through Google's authenticated IAP range; HTTP/HTTPS and WebRTC TCP/UDP 8189 are the only public application ports. RTSP, MediaMTX API, ClickHouse and the coordinator bind to loopback.
- Runtime service account: `clappy-runtime@clappy-cinema-2026-0907.iam.gserviceaccount.com`, with project-scoped Vertex AI user, Speech client and Service Usage consumer. No exported service-account key or developer credentials. Runtime uses metadata-based ADC.
- A trusted Let's Encrypt certificate was issued and installed. No TLS-validation bypass is part of deployment.

## Bounded operation, not a dollar guarantee

The VM is configured to automatically **STOP after 86,400 seconds of runtime**. Automatic restart on failure is disabled. A new manually authorized start resets the 24-hour runtime window. STOP preserves the disk and recordings; **disk storage remains billable while stopped**. Do not leave the retained disk indefinitely without a retention decision. No automatic data deletion is configured.

Budget `84d22336-73df-4b3b-820f-7c8f76b22d19` is a $25 monthly, Clappy-project-only gross-usage alert, excluding credits for conservative visibility. Alert thresholds: 25%, 50%, 80%, 100%. Google budget alerts are delayed notifications, not spending caps. Existing unrelated budgets were not changed.

Hosted daily allowances: 12 productions, 12 takes, 24 renders, 80 AI jobs, 1,000 speech seconds and 20 director-audio requests. A take stops after 50 seconds. One live media rig and one render worker are allowed. A 4 GiB free-space reserve rejects new arm/roll/alternate work without blocking CUT. nginx limits body sizes, request rates and concurrent connections; production WebSockets are capped at eight per production. These remain bounded-demo controls, not general public-service capacity guarantees.

`clappy-guard.timer` checks the default network interface's transmitted-byte counter every ten seconds. Its persistent `/var/lib/clappy-guard/state.json` accumulates across counter resets/boots. At 10 GiB it latches and stops Clappy's coordinator, nginx and MediaMTX, preserving saved data and database files. There can be up to a check interval of overshoot. It measures all VM outbound bytes, not Google billable-egress accounting. Corrupt persisted evidence trips the guard rather than resetting the allowance. Do not reset it or restart tripped services without reviewing resource use.

## Private files

- `/etc/clappy.env`: mode 0600, owned by root; invitation and database password. Do not print or commit it.
- `/opt/clappy/data`: production state, usage ledger, media key/config, sources and recordings. Preserve it across updates.
- Local `data/hosting-access.json`: mode 0600; the invitation fetched over authorized IAP. Never paste into a URL, screenshot, public submission or tool output.
- Local `data/hosting-browser-state.json`: private test-production login, mode 0600. Treat like a password.

## Installation and recovery

The VM startup metadata ran `infra/hosting/bootstrap.sh` once to install system dependencies. The release contains application code, built `dist`, both Python lockfiles and only the owned synthetic source generations—not local sessions, production keys or old recordings.

After successful installation, the one-time startup-script metadata is removed so it cannot stop nginx on a later boot. The checked-in bootstrap also exits immediately if the Clappy systemd unit already exists.

`infra/hosting/install.sh` installs the locked runtimes, generates private secrets only if absent, starts the pinned media/database containers and non-root systemd API, and installs nginx. `scripts/prepare_host.py` refuses to overwrite an existing credential file. TLS issuance is a separate certbot step after DNS and the HTTP challenge are reachable.

The live director now uses `CLAPPY_DIRECTOR_LIVE_MODEL=gemini-2.5-flash-lite`, bounded creative context and a per-take official MCP connection. It still queries current memory before every proposal; it does not cache a fabricated director answer. The first MCP launch can exceed a dialogue beat and is rejected if stale. Warm hosted requests measured approximately 0.9 seconds. Full alternate edits retain `gemini-2.5-flash` and the ADK tool loop. Invalid edit coverage/allocation is rejected rather than silently relabeled as successful.

Check status without printing credentials:

```sh
gcloud compute ssh clappy-demo-1 --project=clappy-cinema-2026-0907 --zone=us-central1-a --tunnel-through-iap --command='sudo systemctl is-active clappy nginx clappy-guard.timer'
curl --fail https://34-133-211-128.sslip.io/api/health
```

To stop compute while preserving recordings:

```sh
gcloud compute instances stop clappy-demo-1 --project=clappy-cinema-2026-0907 --zone=us-central1-a
```

Do not run the full installer over a live take. Do not delete Docker volumes, reset usage/guard ledgers, publish invitations, or copy local ADC credentials to the VM. Updates must preserve database and source-generation paths. Hosted media and AI verification evidence is recorded in `BUILD_STATUS.md`; HTTPS health alone is not end-to-end acceptance.
