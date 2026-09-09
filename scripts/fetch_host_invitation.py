"""Fetch the authorized demo invite over IAP into a private local runtime file."""
import json
import os
from pathlib import Path
import subprocess


def main():
    # SSH output is captured, never printed or sent to a browser URL.
    result = subprocess.run([
        "gcloud", "compute", "ssh", "clappy-demo-1", "--project=clappy-cinema-2026-0907",
        "--zone=us-central1-a", "--tunnel-through-iap", "--quiet",
        "--command=sudo awk -F= '/^CLAPPY_DEMO_ACCESS_KEY=/{print $2}' /etc/clappy.env",
    ], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError("Could not retrieve invitation over authenticated SSH")
    invite = result.stdout.strip()
    if len(invite) < 32 or "\n" in invite:
        raise RuntimeError("Unexpected invitation response")
    path = Path("data/hosting-access.json")
    path.parent.mkdir(exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"origin": "https://34-133-211-128.sslip.io", "invitation": invite}, handle)
    print("Hosting invitation saved privately to data/hosting-access.json; value not displayed.")


if __name__ == "__main__":
    main()
