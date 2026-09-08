import { useEffect, useRef, useState } from "react";
import type { Session } from "./types";
import { markerHeight, markerWidth, readFrameCode } from "./framecode";

type API = (path: string, init?: RequestInit) => Promise<unknown>;
type Probe = {id:string;clock_epoch:string;client_send_ms:number;client_receive_ms:number};

export function useSourceClock(session: Session | null, enabled: boolean, api: API) {
  const [status, setStatus] = useState("Source clock not sampled");
  const browserId = useRef(crypto.randomUUID());
  const take = session?.takes.find(t=>t.id===session.active_take);
  const sessionId=session?.id, takeId=take?.id, tag=take?.source_tag;
  useEffect(()=>{
    if(!enabled || !sessionId || !takeId || !tag)return;
    let disposed=false, busy=false, probe:Probe|null=null;
    const controller=new AbortController();
    // Hold the current wrapper strongly for this take; a weak wrapper cache can
    // disappear between samples even while its native receiver remains alive.
    const receiverEpochs=new Map<HTMLVideoElement,{track:MediaStreamTrack;id:string}>();
    const canvas=document.createElement("canvas");canvas.width=markerWidth;canvas.height=markerHeight;
    const context=canvas.getContext("2d",{willReadFrequently:true});
    if(!context)return;
    const post=async(path:string, body:unknown)=>{
      const request=new AbortController();
      const abort=()=>request.abort();
      controller.signal.addEventListener("abort",abort,{once:true});
      const timeout=window.setTimeout(abort,5000);
      try{return await api(`/api/sessions/${sessionId}/${path}`,{method:"POST",body:JSON.stringify(body),signal:request.signal});}
      finally{clearTimeout(timeout);controller.signal.removeEventListener("abort",abort);}
    };
    const sample=async()=>{
      if(busy || disposed || document.hidden)return;
      busy=true;
      try {
        if(!probe || performance.now()-probe.client_receive_ms>5000) {
          const client_send_ms=performance.now();
          const reply=await post("clock-probe",{browser_id:browserId.current,take_id:takeId}) as {id:string;clock_epoch:string};
          probe={...reply,client_send_ms,client_receive_ms:performance.now()};
        }
        const frames:unknown[]=[];
        document.querySelectorAll<HTMLIFrameElement>(".program-layer iframe[data-camera]").forEach(frame=>{
          const video=frame.contentDocument?.querySelector("video");
          if(!video)return;
          const read_start_ms=performance.now();
          const code=readFrameCode(video,context);
          const read_end_ms=performance.now();
          if(code && code.source_tag===tag && code.camera===frame.dataset.camera) {
            const stream=video.srcObject as MediaStream|null;
            const track=stream?.getVideoTracks()[0];
            if(track) {
              if(receiverEpochs.get(video)?.track!==track)receiverEpochs.set(video,{track,id:crypto.randomUUID()});
              frames.push({camera:code.camera,packet_hex:code.packet_hex,stream_id:receiverEpochs.get(video)!.id,read_start_ms,read_end_ms});
            }
          }
        });
        if(frames.length) {
          await post("frame-reads",{id:crypto.randomUUID(),browser_id:browserId.current,take_id:takeId,
            clock_epoch:probe.clock_epoch,probe_id:probe.id,client_send_ms:probe.client_send_ms,
            client_receive_ms:probe.client_receive_ms,frames});
          if(!disposed)setStatus(`Source frame codes read · ${frames.length}/3 program streams`);
        } else if(!disposed)setStatus("Waiting for readable source frame codes");
      } catch { if(!disposed)setStatus("Source clock sampling unavailable — timing remains estimated"); }
      finally {busy=false;}
    };
    // One small pixel strip per stream per second; no per-frame network traffic.
    const timer=window.setInterval(()=>{void sample();},1000);
    void sample();
    return()=>{disposed=true;clearInterval(timer);controller.abort();};
  },[enabled,sessionId,takeId,tag,api]);
  return status;
}
