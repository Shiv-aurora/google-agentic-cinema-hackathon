import asyncio
import signal
import time
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from services.media.credentials import camera_credentials, password_hash


def recording_coverage(recordings, duration, lost_cameras=()):
    """A decodable fragment alone is not proof of a complete take.

    Duration is a necessary check, not a claim of frame-level synchronization.
    Any observed interruption remains partial even if summed durations suffice.
    """
    return {cam: bool(recordings.get(cam)) and cam not in lost_cameras and
            sum(part["duration"] for part in recordings.get(cam, [])) >= max(0, duration-.25)
            for cam in "abc"}


class MediaHub:
    def __init__(self, data: Path, api_url="http://127.0.0.1:9997", rtsp_url="rtsp://127.0.0.1:8554"):
        self.data, self.api_url, self.rtsp_url = data, api_url, rtsp_url
        self.processes: dict[str, dict[str, asyncio.subprocess.Process]] = {}
        self.logs = {}
        key_path = Path(os.getenv("CLAPPY_MEDIA_ADMIN_KEY_PATH", "data/media-admin.key"))
        if not key_path.is_file():
            raise ValueError("Run .venv/bin/python -m scripts.configure_media_auth first")
        self.admin_key = key_path.read_text().strip()
        self.readers, self.take_users, self.log_tasks = {}, {}, {}
        self.auth_lock = asyncio.Lock()
        self.user_configs = {}

    async def request(self, method, route, **kwargs):
        async with httpx.AsyncClient(timeout=5, auth=("clappy-admin", self.admin_key)) as client:
            response = await client.request(method, self.api_url+route, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

    async def change_users(self, added=(), removed=()):
        async with self.auth_lock:
            config = await self.request("GET", "/v3/config/global/get")
            if config["authMethod"] != "internal" or any(user["user"] == "any" for user in config["authInternalUsers"]):
                raise ValueError("MediaMTX must use the generated credential-protected configuration")
            names = {user["user"] for user in config["authInternalUsers"]}
            if any(name != "clappy-admin" and not name.startswith(("clappy-r-", "clappy-p-")) for name in names):
                raise ValueError("Unexpected media accounts: refusing to overwrite another administrator's configuration")
            unknown = names-{ "clappy-admin" }-set(self.user_configs)
            if unknown and any(path.get("ready") for path in (await self.request("GET", "/v3/paths/list"))["items"]):
                raise ValueError("Another active coordinator owns the media credentials")
            # GET masks passwords. Never PATCH those redacted placeholders back.
            updated = {name: user for name, user in self.user_configs.items() if name not in removed}
            updated.update({user["user"]: user for user in added})
            users = [{"user":"clappy-admin", "pass":password_hash(self.admin_key), "permissions":[{"action":"api"}]}]
            users.extend(updated.values())
            await self.request("PATCH", "/v3/config/global/patch", json={"authInternalUsers": users})
            self.user_configs = updated

    def reader(self, session_id, camera):
        return self.readers[session_id][camera]

    def rtsp_credentials_url(self, path, credentials):
        url = urlsplit(self.rtsp_url)
        return urlunsplit((url.scheme, f"{credentials['user']}:{credentials['pass']}@{url.netloc}", f"/{path}", "", ""))

    async def redact_log(self, stream, handle, password):
        while line := await stream.readline():
            handle.write(line.replace(password.encode(), b"[redacted]"))
            handle.flush()

    async def paths(self):
        return (await self.request("GET", "/v3/paths/list")).get("items", [])

    async def start(self, session_id: str, take_id: str, source_dir=None):
        # Claim the one rig synchronously before the first await. Separate
        # session locks in the API cannot serialize competing productions.
        if self.processes:
            raise ValueError("Another production is using this media rig")
        processes = self.processes[session_id] = {}
        starts = {}
        self.data.joinpath("logs").mkdir(parents=True, exist_ok=True)
        try:
            readers, publishers, users = camera_credentials(take_id)
            await self.change_users(added=users)
            self.readers[session_id] = readers
            self.take_users[session_id] = [user["user"] for user in users]
            for cam in ("a", "b", "c"):
                source = (source_dir or self.data / "fixtures") / f"camera-{cam}.mp4"
                if not source.exists():
                    raise ValueError("Generate the camera fixtures before arming")
                log = (self.data / "logs" / f"{take_id}-{cam}.log").open("wb")
                self.logs[(session_id, cam)] = log
                starts[cam] = time.monotonic()
                processes[cam] = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning", "-re", "-i", str(source),
                    "-c:v", "copy", "-c:a", "libopus", "-b:a", "64k", "-ar", "48000",
                    "-f", "rtsp", "-rtsp_transport", "tcp", self.rtsp_credentials_url(f"{take_id}/{cam}", publishers[cam]),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
                self.log_tasks[(session_id, cam)] = asyncio.create_task(self.redact_log(processes[cam].stderr, log, publishers[cam]["pass"]))
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if any(proc.returncode is not None for proc in processes.values()):
                    raise RuntimeError("A virtual camera exited before its stream was ready. See camera logs.")
                ready = {p["name"] for p in await self.paths() if p.get("ready")}
                if all(f"{take_id}/{cam}" in ready for cam in processes):
                    return {"launch_times": starts, "ready_at": time.monotonic(), "paths": {cam: f"{take_id}/{cam}" for cam in processes}}
                await asyncio.sleep(.15)
            raise RuntimeError("MediaMTX did not confirm all three camera streams")
        except BaseException:
            await self.stop(session_id)
            raise

    async def stop(self, session_id: str):
        processes = self.processes.pop(session_id, {})
        for proc in processes.values():
            if proc.returncode is None:
                proc.send_signal(signal.SIGINT)
        async def reap(cam, proc):
            try:
                await asyncio.wait_for(proc.wait(), 2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            log = self.logs.pop((session_id, cam), None)
            task = self.log_tasks.pop((session_id, cam), None)
            if task:
                await task
            if log:
                log.close()
        # One bounded grace period for the whole rig, not N sequential timeouts.
        await asyncio.gather(*(reap(cam, proc) for cam, proc in processes.items()))
        self.readers.pop(session_id, None)
        users = self.take_users.get(session_id, [])
        if users:
            await self.change_users(removed=users)
            self.take_users.pop(session_id, None)

    async def close(self):
        for session_id in set(self.processes)|set(self.take_users):
            await self.stop(session_id)

    async def inspect_recordings(self, take_id: str):
        # A disappeared publisher closes its last segment asynchronously in the hub.
        await asyncio.sleep(.5)
        result = {}
        for cam in ("a", "b", "c"):
            files = sorted((self.data / "recordings" / take_id / cam).glob("*.mp4"))
            result[cam] = []
            for file in files:
                proc = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(file), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    result[cam].append({"file": str(file.relative_to(self.data)), "duration": float(stdout), "bytes": file.stat().st_size})
        return result
