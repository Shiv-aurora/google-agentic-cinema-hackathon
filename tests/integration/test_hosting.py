from types import SimpleNamespace

import pytest
import yaml

from scripts.prepare_host import configuration
from services.api.storage import require_storage
from scripts.host_guard import advance, LIMIT


def test_host_configuration_uses_adc_private_secrets_and_bounded_allowances():
    env = configuration("clappy.example.com", "203.0.113.1")
    assert "CLAPPY_AUTH_MODE" not in env
    assert len(env["CLAPPY_DEMO_ACCESS_KEY"]) >= 32
    assert env["CLICKHOUSE_PASSWORD"] != "clappy-local-only"
    assert env["CLAPPY_GOOGLE_PROJECT"] == "clappy-cinema-2026-0907"
    assert int(env["CLAPPY_DAILY_TAKES"]) == 12
    for host in ["host;command", "host\ninclude other;", "https://example.com", "../secret"]:
        with pytest.raises(ValueError):
            configuration(host, "203.0.113.1")


def test_host_control_ports_stay_private():
    from pathlib import Path
    compose = yaml.safe_load(Path("infra/hosting/compose.yaml").read_text())
    for service in compose["services"].values():
        assert "@sha256:" in service["image"]
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:") or port in ("8189:8189/udp", "8189:8189/tcp")


def test_storage_reserve_rejects_new_work(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAPPY_MIN_FREE_BYTES", "100")
    monkeypatch.setattr("services.api.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=99))
    with pytest.raises(ValueError, match="CUT remain available"):
        require_storage(tmp_path)
    monkeypatch.setattr("services.api.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=100))
    require_storage(tmp_path)


def test_egress_allowance_survives_counter_reset_and_latches():
    state = advance({}, 100, "boot1")
    assert state["used_bytes"] == 100
    state = advance(state, 150, "boot1")
    assert state["used_bytes"] == 150
    state = advance(state, 20, "boot2")
    assert state["used_bytes"] == 170
    state = advance(state, LIMIT, "boot2")
    assert state["tripped"]
    assert advance(state, 0, "boot3")["tripped"]


def test_egress_guard_fails_closed_without_a_default_route(monkeypatch):
    from scripts import host_guard
    stopped = []
    monkeypatch.setattr(host_guard.subprocess, "check_output", lambda *a, **kw: b"[]")
    monkeypatch.setattr(host_guard.subprocess, "run", lambda command, **kw: stopped.append(command))
    host_guard.main()
    assert len(stopped) == 2
    assert stopped[1] == ["docker", "stop", "clappy-hosted-mediamtx-1"]


def test_egress_guard_attempts_media_stop_if_web_stop_fails(monkeypatch):
    from scripts import host_guard
    stopped = []
    monkeypatch.setattr(host_guard.subprocess, "check_output", lambda *a, **kw: b"[]")
    def stop(command, **kwargs):
        stopped.append(command)
        if command[0] == "systemctl":
            raise host_guard.subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(host_guard.subprocess, "run", stop)
    with pytest.raises(RuntimeError, match="shutdown incomplete"):
        host_guard.main()
    assert len(stopped) == 2
