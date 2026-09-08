"""Dedicated-VM egress circuit breaker. Stops only Clappy services, preserves data."""
import json
import os
from pathlib import Path
import subprocess

LIMIT = 10 * 1024**3


def advance(state, counter, boot):
    previous = state.get("last_counter", 0)
    delta = counter if state.get("boot") != boot or counter < previous else counter - previous
    used = state.get("used_bytes", 0) + delta
    return {"boot": boot, "last_counter": counter, "used_bytes": used,
            "tripped": state.get("tripped", False) or used >= LIMIT, "limit_bytes": LIMIT}


def main():
    # Use the default-route interface, not Docker bridges or process arguments.
    path = Path("/var/lib/clappy-guard/state.json")
    try:
        routes = json.loads(subprocess.check_output(["ip", "-j", "route", "show", "default"], timeout=5))
        interface = routes[0]["dev"]
        if not isinstance(interface, str) or not interface or "/" in interface or interface in (".", ".."):
            raise ValueError("Unexpected interface")
        path.parent.mkdir(mode=0o700, exist_ok=True)
        counter = int(Path(f"/sys/class/net/{interface}/statistics/tx_bytes").read_text())
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        prior = json.loads(path.read_text()) if path.exists() else {}
        state = advance(prior, counter, boot)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        os.replace(temporary, path)
    except Exception:
        # Corrupt guard evidence must not silently reset the allowance.
        state = {"tripped": True}
    if state["tripped"]:
        # Attempt both shutdown paths even when one service manager fails.
        failures = []
        for command in (["systemctl", "stop", "clappy", "nginx"],
                        ["docker", "stop", "clappy-hosted-mediamtx-1"]):
            try:
                subprocess.run(command, check=True, timeout=45)
            except (subprocess.SubprocessError, OSError) as exc:
                failures.append(type(exc).__name__)
        if failures:
            raise RuntimeError("Egress guard shutdown incomplete: " + ", ".join(failures))
        print("Clappy egress guard stopped web, coordinator and media; saved data retained.")


if __name__ == "__main__":
    main()
