#!/usr/bin/env bash
# Run as root after extracting the release to /opt/clappy on the dedicated VM.
set -euo pipefail
cd /opt/clappy
test -x /opt/clappy-tools/bin/uv
test -f dist/index.html
chown -R clappy:clappy /opt/clappy
runuser -u clappy -- /opt/clappy-tools/bin/uv sync --frozen --no-dev --python /usr/bin/python3 --cache-dir /opt/clappy/.cache/uv
runuser -u clappy -- /opt/clappy-tools/bin/uv sync --project infra/mcp-clickhouse --frozen --python /usr/bin/python3 --cache-dir /opt/clappy/.cache/uv
# prepare_host deliberately refuses to overwrite existing active credentials.
if ! test -f /etc/clappy.env; then
    .venv/bin/python -m scripts.prepare_host --hostname "$1" --public-ip "$2"
fi
set -a
source /etc/clappy.env
set +a
runuser -u clappy -m -- .venv/bin/python -m scripts.configure_media_auth
install -d -o clappy -g clappy -m 700 data/recordings
docker compose --env-file /etc/clappy.env -f infra/hosting/compose.yaml up -d
install -m 644 infra/hosting/clappy.service /etc/systemd/system/clappy.service
install -m 644 infra/hosting/clappy-guard.service /etc/systemd/system/clappy-guard.service
install -m 644 infra/hosting/clappy-guard.timer /etc/systemd/system/clappy-guard.timer
systemctl daemon-reload
systemctl enable --now clappy-guard.timer
systemctl enable --now clappy
if test -L /etc/nginx/sites-enabled/default; then
    unlink /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl enable --now nginx
printf '%s\n' 'Clappy installed. HTTPS certificate and external smoke test are still required.'
