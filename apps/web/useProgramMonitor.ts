import { useEffect, useRef, useState } from "react";
import type { CameraId, Session } from "./types";
import { markerWidth, markerHeight, readFrameCode } from "./framecode";

type API = (path: string, init?: RequestInit) => Promise<unknown>;
type Sample = { at: number; mediaTime: number };

/** Reports composed program frames, not wall-clock/source-frame equivalence. */
export function useProgramMonitor(session: Session | null, enabled: boolean, api: API) {
  const browserId = useRef(crypto.randomUUID());
  const [status, setStatus] = useState("Waiting for playback");
  const take = session?.takes.find(t => t.id === session.active_take);
  const decision = take?.decisions?.at(-1);
  const camera = session?.selected_camera;
  const sessionId = session?.id, takeId = take?.id, epoch = take?.clock_epoch;
  const decisionTime = decision?.time;
  const sourceTag = take?.source_tag;

  useEffect(() => {
    if (!enabled || !sessionId || !takeId || !epoch || !camera || decisionTime === undefined) return;
    let stopped = false, frameHandle = 0, video: HTMLVideoElement | null = null;
    let lastFrame = performance.now(), lastFrames = -1, acknowledged = false, reportedStall = false, requestedFallback = false;
    let sample: Record<string, unknown> = {};
    const candidates = new Map<CameraId, Sample>();
    const pending = new Set<AbortController>();
    const canvas = document.createElement("canvas");canvas.width=markerWidth;canvas.height=markerHeight;
    const context = canvas.getContext("2d",{willReadFrequently:true});
    let visible = true;
    const monitorVisible = () => {
      const bounds = document.querySelector(".program-screen")?.getBoundingClientRect();
      return !document.hidden && Boolean(bounds && bounds.bottom > 0 && bounds.top < innerHeight && bounds.right > 0 && bounds.left < innerWidth);
    };
    setStatus("Waiting for displayed frame");
    const report = (kind: "applied" | "stalled", extra: Record<string, unknown>) => {
      const controller = new AbortController();
      pending.add(controller);
      // One bounded request per transition, never one request per video frame.
      const timeout = window.setTimeout(() => controller.abort(), 5000);
      void api(`/api/sessions/${sessionId}/monitor`, { method: "POST", signal: controller.signal,
        body: JSON.stringify({ id: crypto.randomUUID(), browser_id: browserId.current, take_id: takeId,
          clock_epoch: epoch, camera, decision_time: decisionTime, kind, browser_ms: performance.now(), ...extra })
      }).catch(() => { if (!stopped) setStatus("Playback evidence not saved — check connection"); })
        .finally(() => { clearTimeout(timeout); pending.delete(controller); });
    };
    const onFrame: VideoFrameRequestCallback = (now, metadata) => {
      if (stopped || !video) return;
      // WebKit can report a constant mediaTime for WebRTC. Count composed
      // frames instead; do not fabricate a source timestamp from currentTime.
      if (monitorVisible() && !video.paused && !video.ended && metadata.presentedFrames > lastFrames) {
        lastFrames = metadata.presentedFrames;
        lastFrame = performance.now();
        video.dataset.clockEpoch ||= crypto.randomUUID();
        sample = { media_time: metadata.mediaTime, player_epoch: video.dataset.clockEpoch,
          presented_frames: metadata.presentedFrames,
          callback_lateness_ms: now-metadata.expectedDisplayTime };
        if (!acknowledged || reportedStall) {
          let code=null;
          try { if(context && sourceTag)code=readFrameCode(video,context); } catch { /* Keep unverified timing explicit. */ }
          report("applied", {...sample,...(code?.source_tag===sourceTag && code?.camera===camera ? {source_packet_hex:code.packet_hex}:{})});
          acknowledged = true; reportedStall = false; requestedFallback = false;
          setStatus("Displayed frame observed");
        }
      }
      frameHandle = video.requestVideoFrameCallback(onFrame);
    };
    const tick = () => {
      if (!monitorVisible()) {
        lastFrame = performance.now(); candidates.clear();
        if (visible) setStatus("Monitor off screen — observations suspended");
        visible = false;
        return;
      }
      if (!visible) {
        visible = true; acknowledged = false; reportedStall = false; requestedFallback = false;
        lastFrame = performance.now();
        setStatus("Waiting for displayed frame");
      }
      const nextVideo = document.querySelector<HTMLIFrameElement>(".program-layer.visible iframe")?.contentDocument?.querySelector("video") ?? null;
      if (nextVideo !== video) {
        if (video && frameHandle) video.cancelVideoFrameCallback(frameHandle);
        video = nextVideo; lastFrame = performance.now(); lastFrames = -1; acknowledged = false;
        reportedStall = false; requestedFallback = false; sample = {};
        if (video && typeof video.requestVideoFrameCallback === "function") frameHandle = video.requestVideoFrameCallback(onFrame);
        else if (video) { setStatus("Frame observation unavailable in this browser"); return; }
      }
      const progressing: CameraId[] = [];
      // Inspect the actual destination program subscription, not its separate
      // phone-card player: one receiver can stall while the other stays healthy.
      document.querySelectorAll<HTMLIFrameElement>(".program-layer iframe[data-camera]").forEach(frame => {
        const id = frame.dataset.camera as CameraId;
        const candidate = frame.contentDocument?.querySelector("video");
        if (!candidate || candidate.paused || candidate.readyState < 2) return;
        const previous = candidates.get(id), now = performance.now();
        if (previous && now-previous.at < 1000 && candidate.currentTime > previous.mediaTime+.05) progressing.push(id);
        candidates.set(id, { at: now, mediaTime: candidate.currentTime });
      });
      const age = performance.now()-lastFrame;
      if (video && typeof video.requestVideoFrameCallback === "function" && age >= (acknowledged ? 2500 : 10000)) {
        const fallback = progressing.includes("c") && camera !== "c" ? "c" : progressing.find(id => id !== camera);
        // A source can recover after the initial stall had no healthy candidate.
        if (reportedStall && (!fallback || requestedFallback)) return;
        report("stalled", { ...sample, stalled_for_ms: Math.min(age, 60000), fallback_camera: fallback ?? null });
        reportedStall = true;
        requestedFallback = Boolean(fallback);
        setStatus(fallback ? "Playback stalled — requesting camera fallback" : "Playback stalled — no progressing fallback");
      }
    };
    const timer = window.setInterval(tick, 250);
    tick();
    return () => {
      stopped = true; clearInterval(timer);
      if (video && frameHandle) video.cancelVideoFrameCallback(frameHandle);
      pending.forEach(controller => controller.abort());
    };
  }, [enabled, sessionId, takeId, epoch, camera, decisionTime, sourceTag, api]);
  return status;
}
