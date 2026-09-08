"""One-time configuration on a fresh, dedicated Clappy VM; never print secrets."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import secrets


def configuration(host, public_ip):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host) or ".." in host:
        raise ValueError("Invalid public hostname")
    public_ip = str(ipaddress.ip_address(public_ip))
    env = {
        "CLAPPY_DATA_DIR": "/opt/clappy/data",
        "CLAPPY_GOOGLE_PROJECT": "clappy-cinema-2026-0907",
        "CLAPPY_GOOGLE_LOCATION": "global",
        "CLAPPY_GEMINI_MODEL": "gemini-2.5-flash",
        "CLAPPY_DIRECTOR_LIVE_MODEL": "gemini-2.5-flash-lite",
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "CLAPPY_PUBLIC_ORIGIN": "https://" + host,
        "CLAPPY_MEDIA_PUBLIC_IP": public_ip,
        "CLAPPY_MEDIA_ADMIN_KEY_PATH": "/opt/clappy/data/media-admin.key",
        "CLAPPY_DEMO_ACCESS_KEY": secrets.token_urlsafe(32),
        "CLICKHOUSE_PASSWORD": secrets.token_hex(32),
        "CLICKHOUSE_USERNAME": "clappy",
        "CLICKHOUSE_HOST": "127.0.0.1",
        "CLICKHOUSE_PORT": "8123",
        "CLICKHOUSE_SECURE": "false",
        "CLAPPY_DAILY_SESSIONS": "12",
        "CLAPPY_DAILY_TAKES": "12",
        "CLAPPY_DAILY_RENDERS": "24",
        "CLAPPY_DAILY_AI_JOBS": "80",
        "CLAPPY_DAILY_SPEECH_SECONDS": "1000",
        "CLAPPY_DAILY_VOICE_REQUESTS": "20",
        "CLAPPY_MIN_FREE_BYTES": "4294967296",
    }
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--public-ip", required=True)
    args = parser.parse_args()
    env = configuration(args.hostname, args.public_ip)
    # O_EXCL avoids accidentally rotating active invitation/database secrets.
    descriptor = os.open("/etc/clappy.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("".join(f"{key}={value}\n" for key, value in env.items()))
    template = Path("infra/hosting/nginx.conf.template").read_text()
    Path("/etc/nginx/conf.d/clappy.conf").write_text(template.replace("__CLAPPY_HOST__", args.hostname))
    print("Private hosting environment and proxy configuration created; credentials not displayed.")


if __name__ == "__main__":
    main()
