from services.media.credentials import camera_credentials, password_hash
from services.media.hub import MediaHub
import pytest


def test_media_accounts_are_exact_path_and_role_scoped():
    readers, publishers, users = camera_credentials("unique-take")
    assert len(users) == 6
    assert len({item["pass"] for item in users}) == 6
    for cam in "abc":
        for credentials, action in ((readers[cam], "read"), (publishers[cam], "publish")):
            configured = next(user for user in users if user["user"] == credentials["user"])
            assert configured["pass"] == password_hash(credentials["pass"])
            assert configured["permissions"] == [{"action": action, "path": f"unique-take/{cam}"}]
            assert credentials["pass"] not in configured["pass"]


@pytest.mark.asyncio
async def test_config_masks_are_not_written_back_as_passwords(tmp_path, monkeypatch):
    key = "local-unit-test-admin-key-00000000"
    key_path = tmp_path/"admin.key"
    key_path.write_text(key)
    monkeypatch.setenv("CLAPPY_MEDIA_ADMIN_KEY_PATH", str(key_path))
    hub = MediaHub(tmp_path)
    current = [{"user":"clappy-admin","pass":password_hash(key),"permissions":[{"action":"api"}]}]
    async def request(method, route, **kwargs):
        nonlocal current
        if method == "GET":
            return {"authMethod":"internal","authInternalUsers":[{**user,"pass":"**********"} for user in current]}
        current = kwargs["json"]["authInternalUsers"]
    monkeypatch.setattr(hub, "request", request)
    _, _, accounts = camera_credentials("take-one")
    await hub.change_users(added=accounts)
    assert len(current) == 7
    assert current[0]["pass"] == password_hash(key)
    assert all(user["pass"].startswith("sha256:") for user in current)
    await hub.change_users(removed=[user["user"] for user in accounts])
    assert len(current) == 1 and current[0]["pass"] == password_hash(key)


@pytest.mark.asyncio
async def test_rig_claim_excludes_other_productions_before_any_await(tmp_path, monkeypatch):
    import asyncio
    key_path = tmp_path/"admin.key"
    key_path.write_text("local-unit-test-admin-key-00000000")
    monkeypatch.setenv("CLAPPY_MEDIA_ADMIN_KEY_PATH", str(key_path))
    hub = MediaHub(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    async def blocked_auth(**kwargs):
        entered.set()
        await release.wait()
        raise RuntimeError("test stops before creating real publishers")
    monkeypatch.setattr(hub, "change_users", blocked_auth)
    first = asyncio.create_task(hub.start("first", "take-one"))
    await entered.wait()
    try:
        with pytest.raises(ValueError, match="Another production"):
            await hub.start("second", "take-two")
        assert set(hub.processes) == {"first"}
    finally:
        release.set()
        with pytest.raises(RuntimeError, match="test stops"):
            await first
    assert not hub.processes
