import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Clapperboard,
  Download,
  Film,
  Focus,
  Layers,
  LoaderCircle,
  Maximize2,
  Radio,
  Settings2,
  ShieldCheck,
  Square,
  Video,
  Volume2,
  VolumeX,
  Wifi,
  X,
} from "lucide-react";
import type { Camera, CameraId, Edit, Health, Session, Take } from "./types";
import "./style.css";
import { VoiceControl } from "./VoiceControl";
import { useProgramMonitor } from "./useProgramMonitor";
import { useSourceClock } from "./useSourceClock";

const storageKey = "clappy-director-session";
type Credentials = { id: string; token: string };
class ApiError extends Error {
  constructor(message:string, readonly status:number) { super(message); }
}
function clock(seconds = 0) {
  const n = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [page, setPage] = useState<"shoot" | "review">("shoot");
  const [busy, setBusy] = useState(false);
  const [monitorSound,setMonitorSound] = useState(false);
  const masterFrame = useRef<HTMLIFrameElement|null>(null);
  const [error, setError] = useState("");
  const [needsInvite, setNeedsInvite] = useState(false);
  const [invite, setInvite] = useState("");
  const [joining, setJoining] = useState(false);
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(Date.now() / 1000);
  const [sceneOpen, setSceneOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [events, setEvents] = useState<
    { seq: number; kind: string; timestamp: number; payload: unknown }[]
  >([]);
  const auth = useRef<Credentials | null>(null);
  const accept = useCallback(
    (doc: Session) =>
      setSession((old) =>
        old && old.id === doc.id && old.revision > doc.revision ? old : doc,
      ),
    [],
  );

  const api = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(auth.current
          ? { Authorization: `Bearer ${auth.current.token}` }
          : {}),
        ...init.headers,
      },
    });
    if (!response.ok) {
      const body = await response
        .json()
        .catch(() => ({ detail: "Request failed" }));
      throw new ApiError(body.detail || "Request failed", response.status);
    }
    return response.json();
  }, []);

  const playbackStatus = useProgramMonitor(session, session?.state === "RECORDING" && page === "shoot", api);
  const sourceClockStatus = useSourceClock(session, session?.state === "RECORDING" && page === "shoot", api);

  useEffect(() => {
    let disposed = false;
    (async () => {
      try {
        const stored = localStorage.getItem(storageKey);
        if (stored) {
          const old = JSON.parse(stored) as Credentials;
          auth.current = old;
          try {
            const doc = await api(`/api/sessions/${old.id}`);
            if (!disposed) {
              accept(doc);
              setCredentials(old);
            }
            return;
          } catch (exc) {
            if (!(exc instanceof ApiError) || exc.status !== 403) throw exc;
            auth.current = null;
          }
        }
        const result = await api("/api/sessions", { method: "POST" });
        const value = { id: result.session.id, token: result.token };
        localStorage.setItem(storageKey, JSON.stringify(value));
        auth.current = value;
        if (!disposed) {
          accept(result.session);
          setCredentials(value);
        }
      } catch (exc) {
        if (!disposed) {
          if(exc instanceof ApiError && exc.status===403)setNeedsInvite(true);
          else setError((exc as Error).message);
        }
      }
    })();
    return () => {
      disposed = true;
    };
  }, [api, accept]);

  useEffect(() => {
    const poll = () =>
      fetch("/api/health")
        .then((r) => r.json())
        .then(setHealth)
        .catch(() => {});
    poll();
    const timer = setInterval(poll, 10000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!credentials) return;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let ended = false;
    const open = () => {
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/sessions/${credentials.id}/live`,
      );
      socket.onopen = () => {
        socket.send(JSON.stringify({ token: credentials.token }));
        setConnected(true);
      };
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "state") accept(data.session);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!ended) retry = setTimeout(open, 1500);
      };
    };
    open();
    return () => {
      ended = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [credentials, accept]);

  const command = async (kind: string, camera?: CameraId) => {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const result = await api(`/api/sessions/${session.id}/commands`, {
        method: "POST",
        body: JSON.stringify({
          id: crypto.randomUUID(),
          kind,
          camera,
          expected_revision: session.revision,
        }),
      });
      accept(result.session);
      if (kind === "cut") setPage("review");
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const inspect = async () => {
    if (!session) return;
    setEvidenceOpen(true);
    try {
      setEvents(await api(`/api/sessions/${session.id}/events`));
    } catch (exc) {
      setError((exc as Error).message);
    }
  };
  const direct = async (
    note: string,
    kind: "recall" | "edit",
    take_id?: string,
  ) => {
    if (!session) return;
    try {
      const result = await api(`/api/sessions/${session.id}/direction`, {
        method: "POST",
        body: JSON.stringify({ id: crypto.randomUUID(), note, kind, take_id }),
      });
      accept(result.session);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };
  const voice = async(audio:Blob)=>{
    if(!session||!auth.current)throw new Error('Connect to your production first.');
    const form=new FormData();form.append('id',crypto.randomUUID());form.append('take_id',session.active_take||'');form.append('audio',audio,'direction.webm');
    const response=await fetch(`/api/sessions/${session.id}/voice`,{method:'POST',headers:{Authorization:`Bearer ${auth.current.token}`},body:form});
    const result=await response.json();if(!response.ok)throw new Error(result.detail||'Voice direction failed');
    accept(result.session);if(result.action==='review')setPage('review');return result.transcript as string;
  };
  const take = session?.takes.find((t) => t.id === session.active_take);
  const rolling = session?.state === "RECORDING";
  const elapsed =
    rolling && take?.started_at ? now - take.started_at : take?.duration || 0;
  const transitioning =
    session?.state === "STARTING" || session?.state === "STOPPING";
  const preview=(camera:CameraId)=>session?.source_set==='last-train-animatic-v1'?`/api/sessions/${session.id}/preview/${camera}`:undefined;
  useEffect(()=>{if(!rolling)setMonitorSound(false);},[rolling]);
  const toggleSound=async()=>{
    const video=masterFrame.current?.contentDocument?.querySelector('video');
    if(!video){setError('Production audio is still connecting. Try again in a moment.');return;}
    try{video.muted=monitorSound;await video.play();setMonitorSound(!monitorSound);}
    catch{video.muted=true;setError('Click again once the production stream is playing to enable audio.');}
  };

  return (
    <div className="app-shell">
      <aside className="rail">
        <a className="brand-icon" href="/" aria-label="Clappy home">
          <Clapperboard size={23} />
        </a>
        <button
          className={page === "shoot" ? "active" : ""}
          onClick={() => setPage("shoot")}
          title="Production"
        >
          <Video size={21} />
        </button>
        <button
          className={page === "review" ? "active" : ""}
          onClick={() => setPage("review")}
          title="Review takes"
        >
          <Layers size={21} />
        </button>
        <div className="rail-bottom">
          <span className="avatar">SA</span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="wordmark">
            clappy<span>STUDIO</span>
          </div>
          <div className="breadcrumb">
            Productions <span>/</span> {session?.title || "New production"}
          </div>
          <button className="text-button" onClick={inspect}>
            <Radio size={14} />
            <span className={connected ? "dot online" : "dot"} />
            {connected ? "Connected" : "Connecting"}
          </button>
        </header>
        <div className="workspace">
          <div className="production-header">
            <div>
              <div className="eyebrow">YOUR LITTLE FILM CREW</div>
              <h1>
                {session?.title || "Setting the scene…"}{" "}
                <span className="scene-chip">SCENE 01</span>
              </h1>
              <p>Three cameras. One scene. You're in the director's chair.</p>
            </div>
            <button
              className="secondary"
              disabled={!session || rolling || transitioning}
              onClick={() => setSceneOpen(true)}
            >
              <Settings2 size={15} /> Scene settings
            </button>
          </div>
          <div className="workspace-tabs">
            <div>
              <button
                className={page === "shoot" ? "selected" : ""}
                onClick={() => setPage("shoot")}
              >
                <Video size={15} />
                On set
              </button>
              <button
                className={page === "review" ? "selected" : ""}
                onClick={() => setPage("review")}
              >
                <Film size={15} />
                Takes & edits <span>{session?.takes.length || 0}</span>
              </button>
            </div>
            <span className="mode-label">VIRTUAL CAMERA REHEARSAL</span>
          </div>
          {(error || session?.error) && (
            <div className="error-banner" role="alert">
              {error || session?.error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={15} />
              </button>
            </div>
          )}
          {session ? (
            page === "shoot" ? (
              <>
                <div className="shoot-grid">
                  <section className="program-panel">
                    <div className="panel-title">
                      <span>
                        <span
                          className={rolling ? "dot recording" : "dot online"}
                        />{" "}
                        PROGRAM MONITOR
                      </span>
                      <button className="text-button" disabled={!rolling} onClick={toggleSound} aria-label={monitorSound?'Mute production audio':'Listen to production audio'}>
                        {monitorSound?<Volume2 size={14}/>:<VolumeX size={14}/>} Master audio
                      </button>
                      <span>
                        {rolling
                          ? "LIVE"
                          : transitioning
                            ? session.state
                            : "STANDBY"}{" "}
                        <i /> {clock(elapsed)}
                      </span>
                    </div>
                    {rolling && <div className="monitor-health" role="status">{playbackStatus} · {sourceClockStatus}</div>}
                    <div className="program-screen">
                      {session.cameras.map((cam) => (
                        <div
                          key={cam.id}
                          className={`program-layer ${cam.id === session.selected_camera ? "visible" : ""}`}
                        >
                          <Stream
                            sessionId={session.id}
                            camera={cam}
                            path={rolling ? take?.paths?.[cam.id] : undefined}
                            frameRef={cam.id==='c'?masterFrame:undefined}
                            preview={preview(cam.id)}
                          />
                        </div>
                      ))}
                      <div className="program-overlay">
                        <span>
                          <span className="camera-letter">
                            {session.selected_camera.toUpperCase()}
                          </span>
                          {
                            session.cameras.find(
                              (c) => c.id === session.selected_camera,
                            )?.role
                          }{" "}
                          <small>
                            {session.hold ? "HOLDING" : "ON PROGRAM"}
                          </small>
                        </span>
                        <Maximize2 size={16} />
                      </div>
                      {!rolling && (
                        <div className="standby-message">
                          <Focus size={35} />
                          <h2>
                            {transitioning
                              ? "Bringing the crew online…"
                              : session.state === "ARMED"
                                ? "All set. Let’s roll."
                                : "A scene waiting to happen."}
                          </h2>
                          <p>
                            {transitioning
                              ? "Waiting for real media acknowledgments."
                              : "Arm the virtual cameras to begin your rehearsal."}
                          </p>
                        </div>
                      )}
                    </div>
                    <div className="program-caption">
                      <ShieldCheck size={14} />
                      <span>{session.source_set==='last-train-animatic-v1'?'Animatic originals preserved':'Fixture originals preserved'}</span>
                      <span className="push-right">
                        960 × 540 <i /> 30 FPS
                      </span>
                    </div>
                  </section>
                  <section className="script-panel">
                    <div className="panel-title">
                      <span>THE SCREENPLAY</span>
                      <button
                        className="icon-button"
                        onClick={() => setSceneOpen(true)}
                        aria-label="Edit screenplay"
                      >
                        <Settings2 size={14} />
                      </button>
                    </div>
                    <div className="script-heading">
                      {session.script.split("\n")[0]}
                    </div>
                    <div className="script-body">
                      {session.script
                        .split("\n\n")
                        .slice(1)
                        .map((block, i) => (
                          <div
                            className={`script-line ${session.performance?.line?.id === i ? "current" : ""}`}
                            key={i}
                          >
                            <span className="line-num">
                              {String(i + 1).padStart(2, "0")}
                            </span>
                            <div>
                              {block
                                .split("\n")
                                .map((line, j) =>
                                  j === 0 && /^[A-Z ]+$/.test(line) ? (
                                    <h4 key={j}>{line}</h4>
                                  ) : (
                                    <p key={j}>{line}</p>
                                  ),
                                )}
                            </div>
                          </div>
                        ))}
                    </div>
                    <div className="script-footer">
                      <span className={session.performance?.status==='TRACKING'?'dot online':'dot'} />
                      {session.performance?.status==='TRACKING'?`Google speech · ${session.performance.line?.character} · ${Math.round((session.performance.line?.confidence||0)*100)}% match`:session.performance?.status==='LISTENING'?'Listening to production audio':session.performance?.status==='FAILED'?'Speech needs attention':'Scene following awaits dialogue audio'}
                    </div>
                  </section>
                </div>
                <div className="section-label">
                  <span>
                    THE CAMERA CREW <small>3 virtual iPhones</small>
                  </span>
                  <span>Choose a view to cut to it</span>
                </div>
                <div className="camera-grid">
                  {session.cameras.map((cam) => (
                      <CameraCard
                      sessionId={session.id}
                      key={cam.id}
                        camera={cam}
                        preview={preview(cam.id)}
                      selected={cam.id === session.selected_camera}
                      path={rolling ? take?.paths?.[cam.id] : undefined}
                      disabled={busy || (rolling && cam.state !== 'RECORDING')}
                      onSelect={() => command("switch", cam.id)}
                      onHold={() =>
                        command(
                          session.hold && session.selected_camera === cam.id
                            ? "release"
                            : "hold",
                          cam.id,
                        )
                      }
                      holding={
                        session.hold && session.selected_camera === cam.id
                      }
                    />
                  ))}
                </div>
                <div className="direction-bar">
                  <div className="clappy-orb">
                    <Clapperboard size={19} />
                  </div>
                  <div>
                    <strong>{session.note}</strong>
                    <p>
                      {session.auto_enabled?'Google speech → Gemini + ClickHouse · Manual hold takes priority.':'Manual live switching · Enable AI for the dialogue rehearsal.'}
                    </p>
                  </div>
                  <button className="text-button" onClick={inspect}>
                    Production log <ArrowRight size={15} />
                  </button>
                  <button className="secondary" disabled={busy||transitioning||!session.source_set||session.source_set==='charts'} onClick={()=>command(session.auto_enabled?'auto_off':'auto_on')}>
                    {session.auto_enabled?'AI director on':'Enable AI director'}
                  </button>
                </div>
                <div className="transport">
                  <div className="take-counter">
                    <span>SCENE</span>
                    <strong>01</strong>
                    <i />
                    <span>TAKE</span>
                    <strong>
                      {String(take?.number || 1).padStart(2, "0")}
                    </strong>
                  </div>
                  <span className="transport-status">
                    <span
                      className={
                        rolling
                          ? "dot recording"
                          : session.state === "ARMED"
                            ? "dot online"
                            : "dot"
                      }
                    />
                    {session.state === "ARMED"
                      ? "3 cameras ready"
                      : rolling
                        ? "Recording all cameras"
                        : session.state.toLowerCase().replace("_", " ")}
                  </span>
                  <button
                    className={`roll-button ${rolling ? "cut" : ""}`}
                    disabled={
                      busy ||
                      transitioning ||
                      (!health?.media.ready && !rolling)
                    }
                    onClick={() =>
                      command(
                        rolling
                          ? "cut"
                          : session.state === "ARMED"
                            ? "roll"
                            : "arm",
                      )
                    }
                  >
                    {busy ? (
                      <LoaderCircle size={17} className="spin" />
                    ) : rolling ? (
                      <Square size={16} fill="currentColor" />
                    ) : (
                      <span className="record-icon" />
                    )}
                    {transitioning
                      ? session.state === "STARTING"
                        ? "Starting cameras…"
                        : "Saving take…"
                      : rolling
                        ? "Cut"
                        : session.state === "ARMED"
                          ? "Roll cameras"
                          : "Arm cameras"}
                  </button>
                </div>
                <VoiceControl disabled={transitioning||busy} onAudio={voice}/>
                {session.queued_direction&&<div className="queued-direction" role="status"><strong>{session.queued_direction.status}</strong> {session.queued_direction.note} <span>Bound to screenplay line {session.queued_direction.target_line_id+1}.</span></div>}
                <AgentNote
                  session={session}
                  onSend={(note) => direct(note, "recall")}
                />
              </>
            ) : (
              <Review
                session={session}
                onDirect={(note, takeId) => direct(note, "edit", takeId)}
              />
            )
          ) : needsInvite ? (
            <section className="invite-gate">
              <ShieldCheck size={30}/>
              <h2>Your invitation to the director's chair.</h2>
              <p>This demo uses paid Google AI. Enter your invitation code to start a production.</p>
              <form onSubmit={async event=>{
                event.preventDefault();setJoining(true);setError('');
                try{
                  const result=await api('/api/sessions',{method:'POST',headers:{'X-Clappy-Invite':invite}});
                  const value={id:result.session.id,token:result.token};
                  localStorage.setItem(storageKey,JSON.stringify(value));
                  auth.current=value;accept(result.session);setCredentials(value);setNeedsInvite(false);setInvite('');
                }catch(exc){setError((exc as Error).message);}
                finally{setJoining(false);}
              }}>
                <label htmlFor="demo-invite">Invitation code</label>
                <input id="demo-invite" type="password" autoComplete="off" maxLength={256} required value={invite} onChange={event=>setInvite(event.target.value)}/>
                <button className="primary" disabled={joining}>{joining?'Opening your studio…':'Open studio'}<ArrowRight size={16}/></button>
              </form>
              <small>Your invitation code is not saved. Your production key stays on this browser.</small>
            </section>
          ) : (
            <div className="loading">
              {error?<button className="secondary" onClick={()=>location.reload()}>Retry connection</button>:<><LoaderCircle className="spin" /> Connecting to your production…</>}
            </div>
          )}
          <footer>
            <span>
              CLAPPY <i /> A SMALL CREW, A BIGGER PICTURE.
            </span>
            <span>
              Media hub{" "}
              <b className={health?.media.ready ? "good" : ""}>
                {health?.media.ready ? "online" : "offline"}
              </b>{" "}
              <i /> Google AI{" "}
              <b className={health?.ai.ready ? "good" : ""}>
                {health?.ai.ready ? "connected" : "not verified"}
              </b>{" "}
              <i /> ClickHouse{" "}
              <b className={health?.memory.ready ? "good" : ""}>
                {health?.memory.ready ? "online" : "offline"}
              </b>
            </span>
          </footer>
        </div>
      </main>
      {sceneOpen && session && (
        <SceneDialog
          session={session}
          sources={health?.sources||['charts']}
          onClose={() => setSceneOpen(false)}
          onSave={async (title, script, source_set) => {
            try {
              accept(
                await api(`/api/sessions/${session.id}/scene`, {
                  method: "PUT",
                  body: JSON.stringify({ title, script, source_set }),
                }),
              );
              setSceneOpen(false);
            } catch (exc) {
              setError((exc as Error).message);
            }
          }}
        />
      )}
      {evidenceOpen && (
        <div className="modal-backdrop" onClick={() => setEvidenceOpen(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Production log</h2>
              <button
                className="icon-button"
                onClick={() => setEvidenceOpen(false)}
                aria-label="Close production log"
              >
                <X />
              </button>
            </div>
            <p>Actual commands and outcomes from this session.</p>
            <div className="events">
              {events.map((event) => (
                <div className="event" key={event.seq}>
                  <span>
                    {new Date(event.timestamp * 1000).toLocaleTimeString()}
                  </span>
                  <strong>{event.kind}</strong>
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function Stream({ camera, path, frameRef, preview, sessionId }: { camera: Camera; sessionId:string; path?: string; preview?:string; frameRef?:React.RefObject<HTMLIFrameElement|null> }) {
  if(path&&camera.state!=='RECORDING')return <div className="empty-stream" role="status"><span>{camera.role} unavailable</span><small>Live connection interrupted</small></div>;
  if(!path&&preview)return <img className="source-preview" src={preview} alt={`${camera.role} — synthetic animatic preview`}/>;
  if (!path)
    return (
      <div
        className="empty-stream"
        style={{ "--camera-color": camera.color } as React.CSSProperties}
      >
        <div className="frame-guide" />
        <span>{camera.role}</span>
        <small>VIRTUAL CAMERA {camera.id.toUpperCase()}</small>
      </div>
    );
  return (
    <iframe
      ref={frameRef}
      data-camera={camera.id}
      title={`${camera.name} live stream`}
      src={`/api/sessions/${sessionId}/player/${path}`}
      referrerPolicy="no-referrer"
      allow="autoplay; fullscreen"
    />
  );
}

function CameraCard({
  sessionId,
  camera,
  selected,
  path,
  preview,
  onSelect,
  onHold,
  holding,
  disabled,
}: {
  sessionId:string;
  camera: Camera;
  selected: boolean;
  path?: string;
  preview?: string;
  onSelect: () => void;
  onHold: () => void;
  holding: boolean;
  disabled: boolean;
}) {
  return (
    <article
      className={`camera-card ${selected ? "selected" : ""}`}
      style={{ "--camera-color": camera.color } as React.CSSProperties}
    >
      <div className="camera-card-header">
        <span>
          <b>{camera.id.toUpperCase()}</b>
          {camera.name}
        </span>
        <span
          className={
            camera.state === "RECORDING" ? "rec-label" : "camera-state"
          }
        >
          {camera.state === "RECORDING" ? (
            <>
              <span className="dot recording" /> REC
            </>
          ) : (
            camera.state
          )}
        </span>
      </div>
      <button
        className="camera-select"
        disabled={disabled}
        onClick={onSelect}
        aria-label={`Cut to ${camera.role}`}
      >
        <div className="phone-frame">
          <div className="phone-island" />
          <Stream sessionId={sessionId} camera={camera} path={path} preview={preview}/>
          <div className="phone-bottom">
            <span>VIRTUAL IPHONE</span>
            <span className="phone-shutter" />
          </div>
        </div>
        <div className="camera-info">
          <h3>{camera.role}</h3>
          <p>{camera.framing}</p>
          <span className="camera-spec">
            540p preview <i /> {path ? "Live transport" : "Standby"}
          </span>
        </div>
      </button>
      <div className="camera-card-footer">
        <span>
          {selected ? (
            <>
              <span className="dot online" /> ON PROGRAM
            </>
          ) : (
            <>
              <Wifi size={12} /> VIRTUAL SOURCE
            </>
          )}
        </span>
        <button disabled={disabled} onClick={onHold}>
          {holding ? "Release hold" : "Hold shot"}
          {holding ? <Check size={13} /> : <Focus size={13} />}
        </button>
      </div>
    </article>
  );
}

function Review({
  session,
  onDirect,
}: {
  session: Session;
  onDirect: (note: string, takeId: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const take =
    session.takes.find((t) => t.id === selected) || session.takes.at(-1);
  const [editId, setEditId] = useState<string | null>(null);
  const player = useRef<HTMLVideoElement|null>(null);
  const resume = useRef({time:0,playing:false});
  const edit = take?.edits.find((e) => e.id === editId) || take?.edits[0];
  const base = edit ? `/api/sessions/${session.id}/edits/${edit.id}` : "";
  const allocation=(version:Edit|undefined,camera:CameraId)=>version&&take?.duration?100*version.segments.filter(s=>s.camera===camera).reduce((n,s)=>n+s.end-s.start,0)/take.duration:0;
  if (!take)
    return (
      <div className="empty-review">
        <Film size={42} />
        <h2>Your first cut starts on set.</h2>
        <p>Record a take and its timeline will appear here.</p>
      </div>
    );
  return (
    <div className="review-layout">
      <aside className="take-list">
        <div className="eyebrow">YOUR TAKES</div>
        {session.takes.map((t) => (
          <button
            key={t.id}
            className={t.id === take.id ? "selected" : ""}
            onClick={() => {
              setSelected(t.id);
              setEditId(null);
              resume.current={time:0,playing:false};
            }}
          >
            <Film size={17} />
            <div>
              <strong>Take {String(t.number).padStart(2, "0")}</strong>
              <span>
                {clock(t.duration)} · {t.state.toLowerCase()}
              </span>
            </div>
            <ArrowRight size={15} />
          </button>
        ))}
      </aside>
      <section className="review-main">
        <div className="panel-title">
          <span>
            TAKE {String(take.number).padStart(2, "0")} <i />{" "}
            {edit?.name || "Finalizing"}
          </span>
          <span>{clock(take.duration)}</span>
        </div>
        <div className="review-player">
          {edit?.status === "READY" ? (
            <video ref={player} key={edit.id} src={`${base}/video`} controls playsInline onLoadedMetadata={event=>{const video=event.currentTarget;video.currentTime=Math.min(resume.current.time,Math.max(0,video.duration-.1));if(resume.current.playing)void video.play().catch(()=>{});}}/>
          ) : (
            <div className="rendering">
              {edit?.status === "FAILED" || (!edit && take.state === 'INTERRUPTED') ? (
                <>
                  <X />
                  <h2>{edit?'Render needs attention':'Take interrupted'}</h2>
                  <p>{edit?.error || 'The coordinator restarted. Existing source media is preserved; return to On set to record a new take.'}</p>
                </>
              ) : (
                <>
                  <LoaderCircle className="spin" />
                  <h2>Building your first cut…</h2>
                  <p>Your source files are preserved.</p>
                </>
              )}
            </div>
          )}
        </div>
        {edit && (
          <>
            <div className="timeline">
              {edit.segments.map((seg, i) => (
                <div
                  key={i}
                  style={{
                    flex: seg.end - seg.start,
                    background: session.cameras.find((c) => c.id === seg.camera)
                      ?.color,
                  }}
                  title={`${seg.camera.toUpperCase()} · ${clock(seg.start)}–${clock(seg.end)}`}
                >
                  <b>{seg.camera.toUpperCase()}</b>
                  <span>{(seg.end - seg.start).toFixed(1)}s</span>
                </div>
              ))}
            </div>
            <div className="allocation" aria-label="Camera screen-time comparison">
              {session.cameras.map(cam=><div key={cam.id}><span>{cam.role}</span><strong>{edit.id!==take.edits[0]?.id?`${allocation(take.edits[0],cam.id).toFixed(1)}% → `:''}{allocation(edit,cam.id).toFixed(1)}%</strong><div className="allocation-track"><div style={{width:`${allocation(edit,cam.id)}%`,background:cam.color}}/></div></div>)}
            </div>
            <div className="review-meta">
              <span>
                <ShieldCheck size={15} />
                {take.recordings_verified
                  ? "3 independent recordings verified"
                  : "Recording coverage incomplete"}
              </span>
              <span>{edit.sync}</span>
            </div>
            <div className="edit-actions">
              <div>
                {take.edits.map((e) => (
                  <button
                    className={
                      e.id === edit.id ? "secondary selected" : "secondary"
                    }
                    key={e.id}
                    onClick={() => {resume.current={time:player.current?.currentTime||0,playing:!!player.current&&!player.current.paused};setEditId(e.id);}}
                  >
                    {e.name}
                  </button>
                ))}
              </div>
              <div>
                <a
                  className="secondary"
                  href={`${base}/timeline`}
                  download={`${session.title}.otio`}
                >
                  <Download size={14} /> OTIO timeline
                </a>
                {edit.manifest_available ? <a className="secondary" href={`${base}/manifest`} download={`${session.title}-sources.json`}><ShieldCheck size={14}/> Source evidence</a> : null}
                {edit.status === "READY" && (
                  <a
                    className="primary"
                    href={`${base}/video`}
                    download={`${session.title}.mp4`}
                  >
                    <Download size={14} /> Export film
                  </a>
                )}
              </div>
            </div>
            <AgentNote
              session={session}
              editing
              onSend={(note) => onDirect(note, take.id)}
            />
          </>
        )}
      </section>
    </div>
  );
}

function AgentNote({
  session,
  editing = false,
  onSend,
}: {
  session: Session;
  editing?: boolean;
  onSend: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const thinking = sending || session.agent?.status === "THINKING";
  return (
    <section className="agent-note">
      <div className="agent-note-title">
        <Clapperboard size={20} />
        <div>
          <strong>
            {editing ? "A different point of view." : "Talk to your director."}
          </strong>
          <p>
            Gemini + real ClickHouse production memory
            {editing ? " · Your original edit stays untouched." : ""}
          </p>
        </div>
      </div>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setSending(true);
          try {
            await onSend(note);
          } finally {
            setSending(false);
          }
        }}
      >
        <label className="sr-only" htmlFor="director-note">
          Director note
        </label>
        <input
          id="director-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          minLength={3}
          maxLength={1500}
          required
          placeholder={
            editing
              ? "Make a Bella-focused version. Linger on her reaction."
              : "What happened in our last take?"
          }
          disabled={thinking}
        />
        <button className="primary" disabled={thinking}>
          {thinking ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <ArrowRight size={16} />
          )}{" "}
          {thinking
            ? "Consulting memory…"
            : editing
              ? "Create another edit"
              : "Ask Clappy"}
        </button>
      </form>
      {session.agent && (
        <div
          role="status"
          className={`agent-response ${session.agent.status === "FAILED" ? "failed" : ""}`}
        >
          {session.agent.message}
        </div>
      )}
    </section>
  );
}

function SceneDialog({
  session,
  sources,
  onSave,
  onClose,
}: {
  session: Session;
  sources: string[];
  onSave: (title: string, script: string, source_set:string) => Promise<void>;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(session.title);
  const [script, setScript] = useState(session.script);
  const [sourceSet,setSourceSet] = useState(session.source_set||'charts');
  const [saving, setSaving] = useState(false);
  return (
    <div className="modal-backdrop">
      <form
        className="modal"
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave(title, script, sourceSet);
          setSaving(false);
        }}
      >
        <div className="modal-header">
          <h2>Set the scene</h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Close scene settings"
          >
            <X />
          </button>
        </div>
        <label>
          Production title
          <input
            required
            maxLength={100}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Virtual camera sources
          <select value={sourceSet} onChange={e=>setSourceSet(e.target.value as NonNullable<Session['source_set']>)}>
            <option value="charts">Timing test charts · click track</option>
            {sources.includes('last-train-v1')&&<option value="last-train-v1">The last train · Google-voiced dialogue rehearsal</option>}
            {sources.includes('last-train-animatic-v1')&&<option value="last-train-animatic-v1">The last train · cinematic animatic (derived views)</option>}
          </select>
        </label>
        <label>
          Screenplay
          <textarea
            rows={14}
            value={script}
            maxLength={20000}
            onChange={(e) => setScript(e.target.value)}
          />
        </label>
        <button className="primary" disabled={saving}>
          {saving ? "Saving…" : "Save scene"}
          <ArrowRight size={16} />
        </button>
      </form>
    </div>
  );
}

// Reuse the development root when a hook edit invalidates the entry module.
// Otherwise the old tree can retain live sockets and frame observers.
const root = import.meta.hot?.data.root ?? createRoot(document.getElementById("root")!);
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(<App />);
