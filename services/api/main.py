import asyncio
import json
import os
import time
import uuid
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import opentimelineio as otio
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field

from services.api.store import Store
from services.api.memory.clickhouse import ProductionMemory
from services.api.agent.director import Director
from services.api.agent.script import ScriptFollower, script_lines
from services.api.agent.speech import ffmpeg_pcm, recognize_stream
from services.api.agent.voice import transcribe_direction, interpret_direction
from services.api.agent.styles import DIRECTING_PRESETS, directing_style
from services.media.hub import MediaHub, recording_coverage
from services.worker.editor import Segment, make_timeline, render_timeline
from services.worker.alignment import inspect_take
from services.api.usage import UsageBudget, UsageLimitExceeded
from services.api.storage import require_storage
from services.api.access import authorize_invitation, invitation_required, origin_allowed, validate_access_settings
from services.api.monitor import MonitorReport, record_observation
from services.media.framecode import prepare_sources
from services.media.clock import ClockProbeRequest, FrameReadBatch, transform_batch, fit_received_clocks

DATA = Path(os.getenv("CLAPPY_DATA_DIR", "data")).resolve()
store = Store(DATA / "clappy.sqlite")
hub = MediaHub(DATA)
memory = ProductionMemory(store)
usage = UsageBudget(DATA/"usage.sqlite")
director = Director(memory, budget=usage)
listeners: dict[str, set[WebSocket]] = {}
locks: dict[str, asyncio.Lock] = {}
jobs: set[asyncio.Task] = set()
performance_tasks: dict[str, asyncio.Task] = {}
voice_limit = asyncio.Semaphore(2)
render_limit = asyncio.Semaphore(1)
source_prepare_limit = asyncio.Semaphore(1)
clock_probes: dict[str, dict[str, dict]] = {}


@asynccontextmanager
async def lifespan(app):
    validate_access_settings()
    spawn(memory.run())
    yield
    for task in list(jobs):
        task.cancel()
    await asyncio.gather(*list(jobs), return_exceptions=True)
    await hub.close()


app = FastAPI(title="Clappy production coordinator", lifespan=lifespan)


@app.middleware("http")
async def browser_boundary(request: Request, call_next):
    if request.url.path.startswith("/api/") and not origin_allowed(request.headers.get("origin")):
        return JSONResponse({"detail": "This browser origin is not allowed."}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(UsageLimitExceeded)
async def usage_exceeded(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=429)


def spawn(coroutine):
    task = asyncio.create_task(coroutine)
    jobs.add(task)
    task.add_done_callback(jobs.discard)
    return task


def authorize(session_id: str, request: Request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ") or request.cookies.get(f"clappy_{session_id}", "")
    if not store.authorize(session_id, token):
        raise HTTPException(403, "This production session requires its director key")
    return token


def session_cookie(response, request, session_id, token):
    response.set_cookie(f"clappy_{session_id}", token, httponly=True, samesite="strict", max_age=86400,
        path=f"/api/sessions/{session_id}", secure=bool(os.getenv("CLAPPY_PUBLIC_ORIGIN")) or os.getenv("CLAPPY_COOKIE_SECURE", "false")=="true" or request.url.scheme=="https")


async def broadcast(session_id):
    doc = store.get(session_id)
    for ws in list(listeners.get(session_id, set())):
        try:
            await ws.send_json({"type": "state", "session": doc, "server_time": time.time()})
        except Exception:
            listeners.get(session_id, set()).discard(ws)


def active_take(doc):
    return next((take for take in doc["takes"] if take["id"] == doc["active_take"]), None)


def source_dir(source_set):
    return DATA / {"charts": "fixtures", "last-train-v1": "scenes/last-train-v1", "last-train-animatic-v1": "scenes/last-train-animatic-v1", "open-cafe-v1": "scenes/open-cafe-v1"}[source_set]


def take_sources(take):
    # Old takes retain their original generation; no global source replacement.
    return DATA/take["source_directory"] if take.get("source_directory") else source_dir(take.get("source_set", "charts"))


def has_dialogue(source_set):
    return source_set in ("last-train-v1", "last-train-animatic-v1", "open-cafe-v1")


def apply_queued(doc):
    queued = doc.get("queued_direction")
    if not queued or queued["status"] != "DEFERRED" or doc["hold"] or time.monotonic()<doc.get("override_until", 0):
        return False
    if doc["state"] != "RECORDING" or queued["take_id"] != doc["active_take"]:
        queued["status"] = "EXPIRED"
        return False
    proc = hub.processes.get(doc["id"], {}).get(queued["camera"])
    if not proc or proc.returncode is not None or not any(cam["id"] == queued["camera"] and cam["state"] == "RECORDING" for cam in doc["cameras"]):
        queued["status"] = "FAILED"
        return False
    take = active_take(doc)
    at = round((time.monotonic()-take["start_monotonic"])*30)/30
    if doc["selected_camera"] != queued["camera"]:
        decision = {"camera":queued["camera"],"time":at,"reason":queued["note"],"source":"queued-director"}
        if take["decisions"][-1]["time"] == at:
            take["decisions"][-1] = decision
        else:
            take["decisions"].append(decision)
    doc["selected_camera"] = queued["camera"]
    doc["control_epoch"] = doc.get("control_epoch",0)+1
    queued.update(status="APPLIED", applied_at=at)
    doc["note"] = f"Applied your queued direction: {queued['note']}"
    return True


class Command(BaseModel):
    id: str = Field(min_length=8, max_length=100)
    kind: Literal["arm", "roll", "cut", "switch", "hold", "release", "auto_on", "auto_off", "direct"]
    camera: Literal["a", "b", "c"] | None = None
    preset: Literal["classic", "reaction", "patient", "tension"] | None = None
    direction: str | None = Field(default=None, max_length=300)
    expected_revision: int = Field(ge=0)


class SceneUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    script: str = Field(max_length=20000)
    source_set: Literal["charts", "last-train-v1", "last-train-animatic-v1", "open-cafe-v1"] = "charts"


@app.get("/api/health")
async def health():
    try:
        paths = await hub.paths()
        media = {"ready": True, "streams": len(paths)}
    except Exception as exc:
        media = {"ready": False, "error": str(exc)}
    return {"status": "ok", "access_required": invitation_required(), "media": media, "fixtures": (DATA / "fixtures/manifest.json").exists(),
            "ai": {"ready": director.ready, "reason": director.error},
            "memory": {"ready": memory.ready, "reason": memory.error},
            "sources": [name for name in ("charts", "last-train-v1", "last-train-animatic-v1", "open-cafe-v1") if (source_dir(name)/"manifest.json").exists()]}


@app.post("/api/sessions")
async def create_session(response: Response, request: Request):
    authorize_invitation(request.headers.get("x-clappy-invite", ""))
    usage.reserve("session:"+uuid.uuid4().hex, {"sessions": 1})
    doc, token = store.create()
    session_cookie(response, request, doc["id"], token)
    return {"session": doc, "token": token}


@app.get("/api/sessions/{session_id}")
async def session(session_id: str, request: Request, response: Response):
    token = authorize(session_id, request)
    session_cookie(response, request, session_id, token)
    return store.get(session_id)


@app.get("/api/sessions/{session_id}/limits")
async def limits(session_id: str, request: Request):
    authorize(session_id, request)
    return {"period": "UTC day", "remaining": usage.remaining(), "note": "Operation limits, not a dollar spending cap."}


@app.get("/api/sessions/{session_id}/preview/{camera}")
async def source_preview(session_id: str, camera: Literal["a","b","c"], request: Request):
    authorize(session_id, request)
    path = source_dir(store.get(session_id).get("source_set", "charts"))/f"camera-{camera}.jpg"
    if not path.exists():
        raise HTTPException(404, "This source has no picture preview")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/sessions/{session_id}/events")
async def events(session_id: str, request: Request):
    authorize(session_id, request)
    return store.events(session_id)


def live_camera(session_id, take_id, camera):
    doc = store.get(session_id)
    if doc["state"] != "RECORDING" or doc["active_take"] != take_id:
        raise HTTPException(404, "This take is not live")
    take = active_take(doc)
    try:
        return {"path": take["paths"][camera], **hub.reader(session_id, camera)}
    except KeyError:
        raise HTTPException(404, "Camera credentials are unavailable")


@app.get("/api/sessions/{session_id}/media-ticket/{take_id}/{camera}")
async def media_ticket(session_id: str, take_id: str, camera: Literal["a","b","c"], request: Request):
    authorize(session_id, request)
    return live_camera(session_id, take_id, camera)


@app.post("/api/sessions/{session_id}/monitor")
async def monitor_observation(session_id: str, body: MonitorReport, request: Request):
    authorize(session_id, request)
    async with locks.setdefault(session_id, asyncio.Lock()):
        doc = store.get(session_id)
        healthy = {cam["id"] for cam in doc["cameras"] if cam["state"] == "RECORDING"
                   and (proc := hub.processes.get(session_id, {}).get(cam["id"])) and proc.returncode is None}
        try:
            evidence, duplicate, fallback = record_observation(doc, body, time.monotonic(), healthy)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if not duplicate:
            store.save(doc, "monitor."+body.kind, {"take_id": body.take_id, **evidence})
            if fallback:
                await broadcast(session_id)
        return {"accepted": True, "duplicate": duplicate, "fallback_applied": evidence["fallback_applied"]}


@app.post("/api/sessions/{session_id}/clock-probe")
async def clock_probe(session_id: str, body: ClockProbeRequest, request: Request):
    received = time.monotonic()
    authorize(session_id, request)
    async with locks.setdefault(session_id, asyncio.Lock()):
        doc = store.get(session_id)
        if doc["state"] != "RECORDING" or doc["active_take"] != body.take_id:
            raise HTTPException(409, "Clock probe requires this live take")
        take = active_take(doc)
        probes = clock_probes.setdefault(body.take_id, {})
        if any(p["browser_id"] == body.browser_id and received-p["server_send"] < 2 for p in probes.values()):
            raise HTTPException(429, "Clock probes are limited to one per two seconds")
        if len(probes) >= 24:
            probes.pop(next(iter(probes)))
        probe = {"id": uuid.uuid4().hex, "browser_id": body.browser_id, "server_receive": received,
                 "server_send": time.monotonic(), "clock_epoch": take["clock_epoch"]}
        probes[probe["id"]] = probe
        return probe


@app.post("/api/sessions/{session_id}/frame-reads")
async def frame_reads(session_id: str, body: FrameReadBatch, request: Request):
    authorize(session_id, request)
    async with locks.setdefault(session_id, asyncio.Lock()):
        doc = store.get(session_id)
        take = active_take(doc)
        if doc["state"] != "RECORDING" or not take or take["id"] != body.take_id or take.get("clock_epoch") != body.clock_epoch or not take.get("source_tag"):
            raise HTTPException(409, "Source read belongs to an inactive or uncoded take")
        batches = take.setdefault("frame_read_batches", [])
        payload = body.model_dump()
        prior = next((b for b in batches if b["request"]["id"] == body.id), None)
        if prior:
            if prior["request"] != payload:
                raise HTTPException(409, "Frame batch ID was reused with different content")
            return {"accepted": True, "duplicate": True, "frames": len(prior["samples"])}
        if len(batches) >= 180:
            raise HTTPException(429, "This take's source-read allowance is exhausted")
        probe = clock_probes.get(take["id"], {}).get(body.probe_id)
        if not probe:
            raise HTTPException(409, "Clock probe is unavailable")
        try:
            samples = transform_batch(body, probe, take, time.monotonic())
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        batches.append({"request": payload, "probe": probe, "samples": samples})
        store.save(doc, "media.frame.read", {"take_id": take["id"], "samples": samples})
        return {"accepted": True, "duplicate": False, "frames": len(samples)}


@app.get("/api/sessions/{session_id}/player/{take_id}/{camera}")
async def camera_player(session_id: str, take_id: str, camera: Literal["a","b","c"], request: Request):
    authorize(session_id, request)
    live_camera(session_id, take_id, camera)
    nonce = uuid.uuid4().hex
    ticket_url = f"/api/sessions/{session_id}/media-ticket/{take_id}/{camera}"
    html = Path("apps/player/index.html").read_text().replace("__CLAPPY_NONCE__",nonce).replace("__CLAPPY_TICKET_URL__",json.dumps(ticket_url))
    return HTMLResponse(html, headers={"Referrer-Policy":"no-referrer", "Content-Security-Policy":
        f"default-src 'none'; script-src 'self' 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'self'"})


@app.put("/api/sessions/{session_id}/scene")
async def update_scene(session_id: str, body: SceneUpdate, request: Request):
    authorize(session_id, request)
    async with locks.setdefault(session_id, asyncio.Lock()):
        doc = store.get(session_id)
        if doc["state"] in ("STARTING", "RECORDING", "STOPPING"):
            raise HTTPException(409, "Finish the current take before changing the scene")
        if not (source_dir(body.source_set)/"manifest.json").exists():
            raise HTTPException(409, "That source set has not been generated")
        if doc["state"] == "ARMED" and doc.get("source_set") != body.source_set:
            doc["state"] = "DRAFT"
            for camera in doc["cameras"]:
                camera["state"] = "OFFLINE"
        doc.update(title=body.title, script=body.script, source_set=body.source_set)
        store.save(doc, "scene.updated", body.model_dump())
        await broadcast(session_id)
        return doc


async def render_edit(session_id, take_id, edit_id):
    try:
        # Keep CUT responsive and bound CPU-heavy alignment/rendering to one job.
        async with render_limit:
            snapshot = store.get(session_id)
            take_snapshot = next(t for t in snapshot["takes"] if t["id"] == take_id)
            if not take_snapshot.get("alignment"):
                try:
                    report = await asyncio.to_thread(inspect_take, DATA, take_sources(take_snapshot), take_snapshot["recordings"], take_snapshot["source_offsets"], take_snapshot["duration"])
                except Exception as exc:
                    report = {"verified": False, "reason": str(exc), "scope": "Recorded media identity; live command timing remains estimated"}
                (DATA/"alignment").mkdir(exist_ok=True)
                (DATA/"alignment"/f"{take_id}.json").write_text(json.dumps(report, indent=2)+"\n")
                async with locks.setdefault(session_id, asyncio.Lock()):
                    doc = store.get(session_id)
                    take = next(t for t in doc["takes"] if t["id"] == take_id)
                    take["alignment"] = report
                    take["recordings_verified"] = take["recordings_verified"] and report["verified"]
                    if not take["recordings_verified"]:
                        take["state"] = "PARTIAL"
                    store.save(doc, "media.alignment.completed", {"take_id": take_id, **report})
                    await broadcast(session_id)
            info = await asyncio.to_thread(render_timeline, DATA / "edits" / f"{edit_id}.otio", DATA / "renders" / f"{edit_id}.mp4")
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            take = next(t for t in doc["takes"] if t["id"] == take_id)
            edit = next(e for e in take["edits"] if e["id"] == edit_id)
            edit.update(status="READY", output=info)
            edit["sync"] = "Source frames verified · live timing estimated" if take.get("alignment", {}).get("verified") else "Media alignment uncertain · live timing estimated"
            timeline_path = DATA/"edits"/f"{edit_id}.otio"
            manifest = {"schema_version": 1, "session_id": session_id, "take_id": take_id, "edit_id": edit_id,
                "parent_id": edit.get("parent_id"), "source_set": take.get("source_set", "charts"),
                "kind": "synthetic-original-conform", "source_offsets": take["source_offsets"],
                "timing": edit["sync"], "segments": edit["segments"], "alignment": take.get("alignment"),
                "clock_epoch": take.get("clock_epoch"), "monitor_observations": take.get("monitor_observations", []),
                "source_directory": take.get("source_directory"), "source_tag": take.get("source_tag"),
                "frame_read_batches": take.get("frame_read_batches", []), "received_clock_calibration": take.get("received_clock_calibration"),
                "recordings_verified": take["recordings_verified"], "output": info,
                "timeline_sha256": hashlib.sha256(timeline_path.read_bytes()).hexdigest()}
            (DATA/"manifests").mkdir(exist_ok=True)
            (DATA/"manifests"/f"{edit_id}.json").write_text(json.dumps(manifest, indent=2)+"\n")
            edit["manifest_available"] = True
            store.save(doc, "render.completed", {"edit_id": edit_id, **info})
    except Exception as exc:
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            take = next(t for t in doc["takes"] if t["id"] == take_id)
            edit = next(e for e in take["edits"] if e["id"] == edit_id)
            edit.update(status="FAILED", error=str(exc))
            store.save(doc, "render.failed", {"edit_id": edit_id, "error": str(exc)})
    await broadcast(session_id)


async def finish_take(doc, reason="Director called cut"):
    take = active_take(doc)
    if not take:
        raise ValueError("There is no active take")
    doc["state"] = "STOPPING"
    if doc.get("queued_direction", {}).get("status") in ("WAITING", "DEFERRED"):
        doc["queued_direction"]["status"] = "EXPIRED"
    stopped = time.monotonic()
    take["received_clock_calibration"] = fit_received_clocks([sample for batch in take.get("frame_read_batches", []) for sample in batch["samples"]])
    clock_probes.pop(take["id"], None)
    take["duration"] = min(55, max(1/30, round((stopped - take["start_monotonic"]) * 30) / 30))
    store.save(doc, "take.stopping", {"take_id": take["id"], "reason": reason})
    await broadcast(doc["id"])
    task = performance_tasks.pop(doc["id"], None)
    if task:
        task.cancel()
    await hub.stop(doc["id"])
    if task:
        await asyncio.gather(task, return_exceptions=True)
    if doc.get("performance"):
        doc["performance"]["status"] = "STOPPED"
    take["recordings"] = await hub.inspect_recordings(take["id"])
    take["recording_coverage"] = recording_coverage(take["recordings"], take["duration"], take.get("lost_cameras", []))
    take["recordings_verified"] = all(take["recording_coverage"].values())
    decisions = take["decisions"]
    segments = []
    for i, item in enumerate(decisions):
        end = decisions[i+1]["time"] if i+1 < len(decisions) else take["duration"]
        end = min(end, take["duration"])
        if end > item["time"]:
            segments.append(Segment(camera=item["camera"], start=item["time"], end=end, reason=item["reason"]))
    edit_id = uuid.uuid4().hex
    timeline = make_timeline(edit_id, segments, take_sources(take), take["duration"], take["source_offsets"])
    (DATA / "edits").mkdir(exist_ok=True)
    otio.adapters.write_to_file(timeline, str(DATA / "edits" / f"{edit_id}.otio"))
    take["edits"] = [{"id": edit_id, "name": "Live cut", "status": "RENDERING", "segments": [s.model_dump() for s in segments],
                      "source": "Fixture originals", "sync": "Clock estimate — not frame-verified"}]
    take["state"] = "READY" if take["recordings_verified"] else "PARTIAL"
    doc["state"] = "READY"
    doc["hold"] = False
    doc["note"] = "Take saved. Rendering the live cut from preserved fixture originals."
    for cam in doc["cameras"]:
        cam["state"] = "RECORDED" if take["recording_coverage"][cam["id"]] else "PARTIAL" if take["recordings"].get(cam["id"]) else "MISSING"
    store.save(doc, "take.finalized", {"take_id": take["id"], "edit_id": edit_id, "recordings_verified": take["recordings_verified"],
        "duration": take["duration"], "decisions": take["decisions"], "source_offsets": take["source_offsets"],
        "source": "Preserved synthetic fixture originals", "sync": "clock estimate"})
    spawn(render_edit(doc["id"], take["id"], edit_id))


async def watch_cameras(session_id, take_id):
    misses = {cam: 0 for cam in "abc"}
    while True:
        await asyncio.sleep(.5)
        snapshot = store.get(session_id)
        if snapshot["state"] != "RECORDING" or snapshot["active_take"] != take_id:
            return
        try:
            ready = {path["name"] for path in await hub.paths() if path.get("ready")}
        except Exception:
            ready = set()
        processes = hub.processes.get(session_id, {})
        for cam in "abc":
            proc = processes.get(cam)
            misses[cam] = 0 if proc and proc.returncode is None and f"{take_id}/{cam}" in ready else misses[cam]+1
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            if doc["state"] != "RECORDING" or doc["active_take"] != take_id:
                return
            changed = []
            for cam in doc["cameras"]:
                state = "OFFLINE" if misses[cam["id"]] >= 3 else cam["state"]
                if misses[cam["id"]] == 0:
                    state = "RECORDING"
                if cam["state"] != state:
                    cam["state"] = state
                    changed.append(cam["id"])
            if not changed:
                continue
            take = active_take(doc)
            healthy = [cam["id"] for cam in doc["cameras"] if cam["state"] == "RECORDING"]
            lost = [cam for cam in changed if cam not in healthy]
            take["lost_cameras"] = sorted(set(take.get("lost_cameras", [])) | set(lost))
            doc["control_epoch"] = doc.get("control_epoch", 0)+1
            if doc["selected_camera"] not in healthy and healthy:
                fallback = "c" if "c" in healthy else healthy[0]
                at = round((time.monotonic()-take["start_monotonic"])*30)/30
                decision = {"camera": fallback, "time": at, "reason": "Selected camera unavailable", "source": "safety-fallback"}
                if take["decisions"][-1]["time"] == at:
                    take["decisions"][-1] = decision
                else:
                    take["decisions"].append(decision)
                doc.update(selected_camera=fallback, hold=False, override_until=0)
            doc["note"] = "Camera connection changed. Interrupted recordings will be marked partial."
            store.save(doc, "camera.health.changed", {"take_id": take_id, "lost": lost, "healthy": healthy})
            if not healthy:
                try:
                    await finish_take(doc, "All camera streams unavailable")
                except Exception as exc:
                    doc.update(state="INTERRUPTED", error=str(exc))
                    store.save(doc, "take.failed", {"error": str(exc)})
            await broadcast(session_id)


async def auto_stop(session_id, take_id):
    await asyncio.sleep(50)
    async with locks.setdefault(session_id, asyncio.Lock()):
        doc = store.get(session_id)
        if doc["state"] == "RECORDING" and doc["active_take"] == take_id:
            try:
                await finish_take(doc, "Fixture take limit reached")
            except Exception as exc:
                doc["state"] = "INTERRUPTED"
                doc["error"] = str(exc)
                store.save(doc, "take.failed", {"error": str(exc)})
            await broadcast(session_id)


async def follow_performance(session_id, take_id):
    follower = ScriptFollower(store.get(session_id)["script"])
    async def recognized(event):
        if not event["final"] and event["stability"] < .7:
            return
        line = follower.observe(event["text"], final=event["final"])
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            if doc["state"] != "RECORDING" or doc["active_take"] != take_id:
                return
            take = active_take(doc)
            if event["final"]:
                take["transcripts"].append(event)
            if line and line["changed"]:
                doc["performance"] = {"status": "TRACKING", "text": event["text"], "line": line,
                    "line_event_id": uuid.uuid4().hex, "recognized_monotonic": time.monotonic()}
                store.save(doc, "performance.line", {"take_id": take_id, "line": line, "recognition": event})
            elif event["final"]:
                store.save(doc, "performance.transcript", {"take_id": take_id, **event})
            else:
                return
            queued = doc.get("queued_direction")
            if event["final"] and line and queued and queued["status"] == "WAITING" and queued["take_id"] == take_id and queued["target_line_id"] == line["id"]:
                queued["status"] = "DEFERRED"
                apply_queued(doc)
                store.save(doc, "direction.queue.condition_met", dict(queued))
            await broadcast(session_id)
    policy = asyncio.create_task(live_policy(session_id, take_id))
    try:
        await recognize_stream(ffmpeg_pcm(hub.rtsp_credentials_url(f"{take_id}/c", hub.reader(session_id, "c"))), recognized)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            if doc["active_take"] == take_id and doc["state"] == "RECORDING":
                doc["performance"] = {"status": "FAILED", "text": str(exc)}
                store.save(doc, "performance.failed", {"error": str(exc)})
                await broadcast(session_id)
    finally:
        policy.cancel()
        await asyncio.gather(policy, return_exceptions=True)


async def live_policy(session_id, take_id):
    try:
        await live_policy_loop(session_id, take_id)
    finally:
        # MCP contexts are closed by the same task that opened them.
        await director.close_live(session_id)


async def live_policy_loop(session_id, take_id):
    processed = set()
    while True:
        await asyncio.sleep(.25)
        snapshot = store.get(session_id)
        if snapshot["state"] != "RECORDING" or snapshot["active_take"] != take_id:
            return
        if snapshot.get("queued_direction", {}).get("status") == "DEFERRED":
            async with locks.setdefault(session_id, asyncio.Lock()):
                doc = store.get(session_id)
                if apply_queued(doc):
                    store.save(doc, "direction.queue.applied", dict(doc["queued_direction"]))
                    await broadcast(session_id)
            snapshot = store.get(session_id)
        performance = snapshot.get("performance", {})
        line_event = performance.get("line_event_id")
        if not snapshot.get("auto_enabled") or snapshot["hold"] or time.monotonic() < snapshot.get("override_until", 0):
            continue
        decision_key = (line_event, snapshot.get("direction_epoch", 0))
        if not line_event or decision_key in processed:
            continue
        take = active_take(snapshot)
        preset_key, preset = directing_style(snapshot)
        if time.monotonic()-take["start_monotonic"]-take["decisions"][-1]["time"] < preset["minimum_hold"]:
            continue
        processed.add(decision_key)
        started = time.monotonic()
        try:
            live_note = snapshot.get("live_direction", "").strip()
            instruction = (f"Choose a shot using the {preset['name']} preset: {preset['prompt']} "
                           f"Persistent live direction: {live_note or 'none'}. Use the current recognized line and recent coverage.")
            result = await director.ask(snapshot, instruction, live=True)
            async with locks.setdefault(session_id, asyncio.Lock()):
                doc = store.get(session_id)
                if doc["state"] != "RECORDING" or doc["active_take"] != take_id:
                    continue
                if (doc.get("control_epoch") != snapshot.get("control_epoch") or doc["hold"] or
                    not doc.get("auto_enabled") or doc.get("performance", {}).get("line_event_id") != line_event or time.monotonic()-started > 8):
                    store.save(doc, "agent.live.rejected", {"reason": "Proposal expired or production changed", **result})
                    continue
                choice = result["response"]
                proc = hub.processes.get(session_id, {}).get(choice["camera"])
                if not proc or proc.returncode is not None or not any(cam["id"] == choice["camera"] and cam["state"] == "RECORDING" for cam in doc["cameras"]):
                    store.save(doc, "agent.live.rejected", {"reason": "Proposed camera is unavailable", **result})
                    continue
                take = active_take(doc)
                if choice["camera"] != doc["selected_camera"]:
                    at = round((time.monotonic()-take["start_monotonic"])*30)/30
                    take["decisions"].append({"camera": choice["camera"], "time": at, "reason": choice["reason"], "source": "gemini", "line_event_id": line_event})
                doc["selected_camera"] = choice["camera"]
                doc["note"] = choice["reason"]
                store.save(doc, "agent.live.applied", {"take_id": take_id, "line_event_id": line_event, **result})
                await broadcast(session_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with locks.setdefault(session_id, asyncio.Lock()):
                doc = store.get(session_id)
                if doc["state"] == "RECORDING" and doc["active_take"] == take_id:
                    doc["note"] = "AI direction unavailable. Manual camera controls remain live."
                    store.save(doc, "agent.live.failed", {"error": str(exc)})
                    await broadcast(session_id)


@app.post("/api/sessions/{session_id}/commands")
async def command(session_id: str, body: Command, request: Request):
    authorize(session_id, request)
    async with locks.setdefault(session_id, asyncio.Lock()):
        try:
            previous = store.command(session_id, body.id, body.model_dump())
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if previous is not None:
            if "error" in previous:
                raise HTTPException(409, previous["error"])
            return previous
        doc = store.get(session_id)
        try:
            if doc["revision"] != body.expected_revision and body.kind in ("arm", "roll"):
                raise ValueError("Production changed. Refresh before applying this command.")
            doc["error"] = None
            if body.kind == "arm":
                require_storage(DATA)
                if doc["state"] not in ("DRAFT", "READY", "INTERRUPTED"):
                    raise ValueError("Cannot arm during another production action")
                await hub.paths()
                if not (source_dir(doc.get("source_set", "charts")) / "manifest.json").exists():
                    raise ValueError("Camera fixtures are not available")
                async with source_prepare_limit:
                    prepared = await asyncio.to_thread(prepare_sources, source_dir(doc.get("source_set", "charts")), DATA/"framecoded")
                doc["prepared_source_directory"] = str(prepared.relative_to(DATA))
                doc["state"] = "ARMED"
                doc["note"] = "Three virtual cameras armed. Ready when you are."
                for cam in doc["cameras"]:
                    cam["state"] = "READY"
            elif body.kind == "roll":
                require_storage(DATA)
                if doc["state"] != "ARMED":
                    raise ValueError("Arm the cameras before rolling")
                if hub.processes:
                    raise ValueError("Another production is using this local media rig")
                charges = {"takes": 1, "renders": 1}
                if has_dialogue(doc.get("source_set")):
                    charges["speech_seconds"] = 60
                usage.reserve(f"roll:{session_id}:{body.id}", charges)
                prepared = DATA/doc["prepared_source_directory"]
                manifest = json.loads((prepared/"manifest.json").read_text())
                take = {"id": uuid.uuid4().hex, "number": len(doc["takes"])+1, "state": "STARTING", "created_at": time.time(), "edits": [], "source_set": doc.get("source_set", "charts"), "transcripts": [],
                        "source_directory": doc["prepared_source_directory"], "source_tag": manifest["source_tag"],
                        "source_frame_counts": {camera["id"]: camera["frame_code_verification"]["frames"] for camera in manifest["cameras"]}, "frame_read_batches": []}
                doc["takes"].append(take)
                doc["active_take"] = take["id"]
                doc["state"] = "STARTING"
                store.save(doc, "take.starting", {"take_id": take["id"]})
                await broadcast(session_id)
                media = await hub.start(session_id, take["id"], take_sources(take))
                take.update(state="RECORDING", clock_epoch=uuid.uuid4().hex, monitor_observations=[], start_monotonic=media["ready_at"], started_at=time.time(), paths=media["paths"],
                            source_offsets={cam: media["ready_at"]-started for cam,started in media["launch_times"].items()},
                            decisions=[{"camera": doc["selected_camera"], "time": 0, "reason": "Opening shot"}])
                doc["state"] = "RECORDING"
                doc["note"] = "Rolling. Select a camera to make the live cut."
                for cam in doc["cameras"]:
                    cam["state"] = "RECORDING"
                spawn(auto_stop(session_id, take["id"]))
                spawn(watch_cameras(session_id, take["id"]))
                if has_dialogue(take["source_set"]):
                    doc["performance"] = {"status": "LISTENING", "text": "Listening to camera C production audio…"}
                    performance_tasks[session_id] = spawn(follow_performance(session_id, take["id"]))
            elif body.kind == "cut":
                if doc["state"] != "RECORDING":
                    raise ValueError("There is no recording take to stop")
                await finish_take(doc)
            elif body.kind in ("switch", "hold"):
                if not body.camera:
                    raise ValueError("Choose a camera")
                if doc["state"] in ("STARTING", "STOPPING"):
                    raise ValueError("Wait for the current production transition")
                if doc["state"] == "RECORDING":
                    proc = hub.processes.get(session_id, {}).get(body.camera)
                    camera = next(cam for cam in doc["cameras"] if cam["id"] == body.camera)
                    if not proc or proc.returncode is not None or camera["state"] != "RECORDING":
                        raise ValueError("That camera is unavailable. Choose a recording camera.")
                if doc["selected_camera"] != body.camera and doc["state"] == "RECORDING":
                    take = active_take(doc)
                    at = round((time.monotonic()-take["start_monotonic"]) * 30)/30
                    if at == take["decisions"][-1]["time"]:
                        take["decisions"][-1]["camera"] = body.camera
                    else:
                        take["decisions"].append({"camera": body.camera, "time": at, "reason": "Manual director selection"})
                doc["selected_camera"] = body.camera
                doc["hold"] = body.kind == "hold"
                role = next(c["role"] for c in doc["cameras"] if c["id"] == body.camera)
                doc["note"] = f"{'Holding' if doc['hold'] else 'On'} {role}."
            elif body.kind in ("auto_on", "auto_off"):
                if body.kind == "auto_on" and not has_dialogue(doc.get("source_set")):
                    raise ValueError("Select the dialogue rehearsal sources in Scene settings first")
                doc["auto_enabled"] = body.kind == "auto_on"
                doc["note"] = "Gemini will direct from actual recognized dialogue." if doc["auto_enabled"] else "Manual direction."
            elif body.kind == "direct":
                if body.preset is None and body.direction is None:
                    raise ValueError("Choose a directing preset or enter a live direction")
                if body.preset is not None:
                    doc["directing_preset"] = body.preset
                if body.direction is not None:
                    doc["live_direction"] = body.direction.strip()
                doc["direction_epoch"] = doc.get("direction_epoch", 0)+1
                preset_name = DIRECTING_PRESETS[doc.get("directing_preset", "classic")]["name"]
                doc["note"] = (f"{preset_name}. {doc['live_direction']}" if doc.get("live_direction")
                               else f"{preset_name} selected.")
            else:
                doc["hold"] = False
                doc["note"] = "Hold released."
            doc["control_epoch"] = doc.get("control_epoch", 0)+1
            if body.kind == "switch":
                doc["override_until"] = time.monotonic()+5
            elif body.kind == "release":
                doc["override_until"] = 0
                if apply_queued(doc):
                    store.save(doc, "direction.queue.applied", dict(doc["queued_direction"]))
            store.save(doc, f"command.{body.kind}.applied", {"command_id": body.id, "camera": body.camera,
                       "preset": body.preset, "direction": body.direction, "take_id": doc["active_take"]})
            result = {"session": doc, "command_id": body.id, "status": "applied"}
            store.complete(session_id, body.id, result)
            await broadcast(session_id)
            return result
        except Exception as exc:
            if doc["state"] in ("STARTING", "STOPPING"):
                await hub.stop(session_id)
                doc["state"] = "INTERRUPTED"
            doc["error"] = str(exc)
            store.save(doc, "command.failed", {"command_id": body.id, "error": str(exc)})
            store.complete(session_id, body.id, {"error": str(exc)})
            await broadcast(session_id)
            raise HTTPException(429 if isinstance(exc, UsageLimitExceeded) else 409, str(exc))


@app.get("/api/sessions/{session_id}/edits/{edit_id}/{artifact}")
async def edit_file(session_id: str, edit_id: str, artifact: Literal["video", "timeline", "manifest"], request: Request):
    authorize(session_id, request)
    doc = store.get(session_id)
    if not any(edit["id"] == edit_id for take in doc["takes"] for edit in take.get("edits", [])):
        raise HTTPException(404, "Edit not found")
    folder, extension = {"video": ("renders", "mp4"), "timeline": ("edits", "otio"), "manifest": ("manifests", "json")}[artifact]
    path = DATA / folder / f"{edit_id}.{extension}"
    if not path.exists():
        raise HTTPException(404, "Artifact is not ready")
    return FileResponse(path, media_type="video/mp4" if artifact == "video" else "application/json")


class DirectionRequest(BaseModel):
    id: str = Field(min_length=8, max_length=100)
    note: str = Field(min_length=3, max_length=1500)
    kind: Literal["recall", "edit"] = "recall"
    take_id: str | None = None


@app.post("/api/sessions/{session_id}/voice")
async def voice_direction(session_id: str, request: Request, audio: UploadFile = File(...),
                          id: str = Form(..., min_length=8, max_length=80), take_id: str = Form("")):
    authorize(session_id, request)
    content = await audio.read(2_000_001)
    if len(content)>2_000_000:
        raise HTTPException(413, "Director recordings must be under 2 MB and 12 seconds")
    signature = {"route": "voice", "audio_sha256": hashlib.sha256(content).hexdigest(), "take_id": take_id}
    reserved = False
    transcript, intent = None, None
    try:
        previous = store.command(session_id, id, signature)
        if previous:
            if "error" in previous:
                raise ValueError(previous["error"])
            return previous
        reserved = True
        async with voice_limit:
            usage.reserve(f"voice:{session_id}:{id}", {"voice_requests": 1, "speech_seconds": 12, "ai_jobs": 1})
            started = time.monotonic()
            snapshot = store.get(session_id)
            transcript = await transcribe_direction(content)
            intent = await interpret_direction(transcript, snapshot["selected_camera"])
            current = store.get(session_id)
            if intent.kind not in ("replay", "edit") and (current["active_take"] or "") != take_id:
                raise ValueError("The take changed while this direction was being recognized. Please repeat it.")
            if intent.kind == "unknown":
                raise ValueError("That direction was ambiguous or unsupported. Please repeat one clear production instruction.")
            if intent.kind == "queue":
                async with locks.setdefault(session_id, asyncio.Lock()):
                    doc = store.get(session_id)
                    if doc["state"] != "RECORDING" or not has_dialogue(doc.get("source_set")) or not intent.camera or not intent.after_character:
                        raise ValueError("Queued direction requires a dialogue take, camera, and named character")
                    current_line = doc.get("performance", {}).get("line", {}).get("id", -1)
                    target = next((line for line in script_lines(doc["script"]) if line["id"]>current_line and line["character"]==intent.after_character), None)
                    if not target:
                        raise ValueError(f"No future {intent.after_character.title()} line remains in this screenplay")
                    doc["queued_direction"] = {"status":"WAITING","take_id":doc["active_take"],"target_line_id":target["id"],
                        "character":intent.after_character,"camera":intent.camera,"note":transcript}
                    doc["control_epoch"] = doc.get("control_epoch",0)+1
                    store.save(doc,"direction.queued",dict(doc["queued_direction"]))
                    result = {"session":doc}
            elif intent.kind == "edit":
                result = await direction(session_id, DirectionRequest(id=id+"-edit", note=transcript, kind="edit", take_id=current["active_take"]), request)
                result["action"] = "review"
            elif intent.kind == "replay":
                result = {"session": current, "action": "review"}
            else:
                result = await command(session_id, Command(id=id+"-control", kind=intent.kind, camera=intent.camera,
                    preset=intent.preset, direction=transcript if intent.kind == "direct" else None,
                    expected_revision=current["revision"]), request)
                if intent.kind == "cut":
                    result["action"] = "review"
            async with locks.setdefault(session_id, asyncio.Lock()):
                doc = store.get(session_id)
                doc["voice"] = {"transcript": transcript, "intent": intent.model_dump(), "elapsed": round(time.monotonic()-started, 3)}
                store.save(doc, "voice.applied", doc["voice"])
                result.update(session=doc, transcript=transcript)
                store.complete(session_id, id, result)
                await broadcast(session_id)
            return result
    except Exception as exc:
        message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
        if reserved:
            store.complete(session_id, id, {"error": message})
            async with locks.setdefault(session_id, asyncio.Lock()):
                doc = store.get(session_id)
                doc["voice"] = {"status":"FAILED","transcript":transcript,"intent":intent.model_dump() if intent else None,"error":message}
                store.save(doc, "voice.failed", doc["voice"])
                await broadcast(session_id)
        raise HTTPException(429 if isinstance(exc, UsageLimitExceeded) else 409, message)


async def direct_job(snapshot, body):
    session_id = snapshot["id"]
    try:
        result = await director.ask(snapshot, body.note, edit=body.kind == "edit")
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            if body.kind == "edit":
                take = next(t for t in doc["takes"] if t["id"] == body.take_id)
                proposal = result["response"]
                segments = [Segment.model_validate(s) for s in proposal["segments"]]
                edit_id = uuid.uuid4().hex
                timeline = await asyncio.to_thread(make_timeline, edit_id, segments, take_sources(take), take["duration"], take["source_offsets"])
                (DATA / "edits").mkdir(exist_ok=True)
                otio.adapters.write_to_file(timeline, str(DATA / "edits" / f"{edit_id}.otio"))
                take["edits"].append({"id": edit_id, "parent_id": take["edits"][0]["id"], "name": proposal["name"],
                    "brief": body.note,
                    "status": "RENDERING", "segments": proposal["segments"], "explanation": proposal["explanation"],
                    "source": "Fixture originals", "sync": "Clock estimate — not frame-verified", "model": result["model"]})
                doc["agent"] = {"status": "READY", "message": proposal["explanation"], "edit_id": edit_id}
                spawn(render_edit(session_id, take["id"], edit_id))
            else:
                doc["agent"] = {"status": "READY", "message": result["response"]}
            store.save(doc, "agent.completed", {"request_id": body.id, "kind": body.kind, **result})
    except Exception as exc:
        async with locks.setdefault(session_id, asyncio.Lock()):
            doc = store.get(session_id)
            doc["agent"] = {"status": "FAILED", "message": str(exc)}
            store.save(doc, "agent.failed", {"request_id": body.id, "error": str(exc)})
    await broadcast(session_id)


@app.post("/api/sessions/{session_id}/direction", status_code=202)
async def direction(session_id: str, body: DirectionRequest, request: Request):
    authorize(session_id, request)
    async with locks.setdefault(session_id, asyncio.Lock()):
        doc = store.get(session_id)
        if store.db.execute("SELECT 1 FROM commands WHERE session_id=? AND id=?", (session_id, body.id)).fetchone():
            try:
                return store.command(session_id, body.id, {"route": "direction", **body.model_dump()})
            except ValueError as exc:
                raise HTTPException(409, str(exc))
        if doc.get("agent", {}).get("status") == "THINKING":
            raise HTTPException(409, "Clappy is still working on the previous note")
        if body.kind == "edit":
            take = next((t for t in doc["takes"] if t["id"] == body.take_id), None)
            if not take or take["state"] not in ("READY", "PARTIAL") or not take.get("edits"):
                raise HTTPException(409, "Choose a finalized take to redirect")
            try:
                require_storage(DATA)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            usage.reserve(f"edit:{session_id}:{body.id}", {"renders": 1})
        try:
            previous = store.command(session_id, body.id, {"route": "direction", **body.model_dump()})
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if previous:
            return previous
        doc["agent"] = {"status": "THINKING", "message": "Consulting this production's ClickHouse history…"}
        store.save(doc, "director.note", body.model_dump())
        snapshot = json.loads(json.dumps(doc))
        if body.take_id:
            snapshot["active_take"] = body.take_id
        result = {"session": doc, "status": "accepted", "request_id": body.id}
        store.complete(session_id, body.id, result)
        spawn(direct_job(snapshot, body))
        await broadcast(session_id)
        return result


@app.websocket("/api/sessions/{session_id}/live")
async def live(ws: WebSocket, session_id: str):
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 5)
        if not store.authorize(session_id, auth.get("token", "")):
            await ws.close(code=4403)
            return
        if len(listeners.get(session_id, ())) >= 8:
            await ws.close(code=4429)
            return
        listeners.setdefault(session_id, set()).add(ws)
        await ws.send_json({"type": "state", "session": store.get(session_id), "server_time": time.time()})
        while True:
            message = await ws.receive_json()
            if message.get("type") == "ping":
                await ws.send_json({"type": "pong", "server_time": time.time(), "echo": message.get("time")})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        listeners.get(session_id, set()).discard(ws)
