#!/usr/bin/env bash
# Run only on Clappy's fresh dedicated Ubuntu 24.04 VM. No application secrets.
set -euo pipefail
if test -f /etc/systemd/system/clappy.service; then
    exit 0 # Never stop a configured deployment on a later boot.
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends python3-venv ffmpeg docker.io docker-compose-v2 nginx certbot python3-certbot-nginx ca-certificates
id clappy >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/clappy --shell /usr/sbin/nologin clappy
install -d -o clappy -g clappy -m 755 /opt/clappy
python3 -m venv /opt/clappy-tools
/opt/clappy-tools/bin/pip install uv==0.6.7
systemctl enable --now docker
# nginx remains stopped until the validated app configuration and TLS are ready.
systemctl stop nginx
