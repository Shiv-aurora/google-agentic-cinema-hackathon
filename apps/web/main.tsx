import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Brain,
  Check,
  ChevronDown,
  Clapperboard,
  Download,
  Film,
  Focus,
  Layers,
  LoaderCircle,
  Maximize2,
  MessageCircle,
  Moon,
  Radio,
  Sparkles,
  Settings2,
  ShieldCheck,
  Square,
  Sun,
  Video,
  Volume2,
  VolumeX,
  Wifi,
  X,
} from "lucide-react";
import type { Camera, CameraId, DirectingPreset, Edit, Health, Session, Take } from "./types";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/manrope";
import "./style.css";
import "./polish.css";
import "./themes.css";
import scenePlate from "../../assets/demo/open-cafe-v1/scene-preview.jpg";
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

const directingPresets: {id: DirectingPreset; name: string; short: string; description: string}[] = [
  {id: "classic", name: "Classic coverage", short: "Balanced dialogue", description: "Establish wide, then use clear shot-reverse-shot coverage."},
  {id: "reaction", name: "Reaction first", short: "Listener-led", description: "Let the listener carry the emotional turns."},
  {id: "patient", name: "Wide and patient", short: "Long master shots", description: "Prefer the two-shot and cut only for a meaningful beat."},
  {id: "tension", name: "Rising tension", short: "Tightening pace", description: "Begin composed, then move closer as the exchange develops."},
];

const styleLabBriefs = [
  {id: "reaction", name: "Reaction first", note: "[STYLE LAB: reaction] Recut this performance as an intimate, listener-led film. Favor the emotional reaction after consequential lines and use patient close-ups."},
  {id: "tension", name: "Rising tension", note: "[STYLE LAB: tension] Recut this same performance with escalating tension. Begin composed and wide, then progressively tighten the coverage and pace."},
] as const;

function directorFingerprint(session: Session) {
  const samples: {camera: CameraId; duration: number}[] = [];
  let manualCuts = 0;
  for (const take of session.takes) {
    const decisions = take.decisions || [];
    decisions.forEach((decision, index) => {
      if (decision.source === "gemini" || decision.source === "queued-director" || decision.source === "safety-fallback") return;
      if (index > 0 || decision.reason === "Manual director selection") manualCuts += 1;
      const end = decisions[index + 1]?.time ?? take.duration ?? decision.time;
      if (end > decision.time) samples.push({camera: decision.camera, duration: end - decision.time});
    });
  }
  if (manualCuts < 2 || samples.length < 2) return null;
  const total = samples.reduce((sum, shot) => sum + shot.duration, 0) || 1;
  const wide = samples.filter((shot) => shot.camera === "c").reduce((sum, shot) => sum + shot.duration, 0) / total;
  const tom = samples.filter((shot) => shot.camera === "a").reduce((sum, shot) => sum + shot.duration, 0);
  const bella = samples.filter((shot) => shot.camera === "b").reduce((sum, shot) => sum + shot.duration, 0);
  const average = total / samples.length;
  const framing = wide > .48 ? "patient master shots" : wide < .22 ? "intimate close coverage" : "balanced coverage";
  const rhythm = average < 3.2 ? "quick, decisive cuts" : average > 5.5 ? "measured holds" : "a natural dialogue rhythm";
  const subject = bella > tom * 1.25 ? " and lean toward Bella's reactions" : tom > bella * 1.25 ? " and lean toward Tom's reactions" : "";
  return {
    summary: `You favor ${framing}, ${rhythm}${subject}.`,
    instruction: `Direct in my learned style: favor ${framing}, use ${rhythm}${subject}. Preserve meaningful reactions and avoid mechanical cutting.`,
    manualCuts,
  };
}

function App() {
  const [theme, setTheme] = useState<'light'|'dark'>(() => {
    try { return localStorage.getItem('clappy-theme') === 'dark' ? 'dark' : 'light'; }
    catch { return 'light'; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('clappy-theme', theme); } catch { /* Browsing without storage remains usable. */ }
  }, [theme]);
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
  const [directorOpen, setDirectorOpen] = useState(false);
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

  const command = async (kind: string, camera?: CameraId, options: {preset?:DirectingPreset;direction?:string} = {}) => {
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
          ...options,
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
  const createStyleLab = async (
    takeId: string,
    onProgress: (completed: number, total: number) => void,
  ) => {
    if (!session) return;
    const total = styleLabBriefs.length;
    let completed = 0;
    for (const style of styleLabBriefs) {
      let current = (await api(`/api/sessions/${session.id}`)) as Session;
      const currentTake = current.takes.find((item) => item.id === takeId);
      if (currentTake?.edits.some((item) => item.brief?.includes(`[STYLE LAB: ${style.id}]`))) {
        completed += 1;
        onProgress(completed, total);
        continue;
      }
      const priorCount = currentTake?.edits.length || 0;
      const accepted = await api(`/api/sessions/${session.id}/direction`, {
        method: "POST",
        body: JSON.stringify({
          id: crypto.randomUUID(),
          note: style.note,
          kind: "edit",
          take_id: takeId,
        }),
      });
      accept(accepted.session);
      for (let attempt = 0; attempt < 75; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 800));
        current = await api(`/api/sessions/${session.id}`) as Session;
        accept(current);
        const updatedTake = current.takes.find((item) => item.id === takeId);
        if (current.agent?.status === "FAILED") throw new Error(current.agent.message);
        if ((updatedTake?.edits.length || 0) > priorCount && current.agent?.status !== "THINKING") break;
        if (attempt === 74) throw new Error("Clappy is taking longer than expected to create the comparison.");
      }
      completed += 1;
      onProgress(completed, total);
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
  const preview=(camera:CameraId)=>session&&['last-train-animatic-v1','open-cafe-v1'].includes(session.source_set||'')?`/api/sessions/${session.id}/preview/${camera}`:undefined;
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
          disabled={!session}
          aria-pressed={page === "shoot"}
        >
          <Video size={21} />
        </button>
        <button
          className={page === "review" ? "active" : ""}
          onClick={() => setPage("review")}
          title="Review takes"
          disabled={!session}
          aria-pressed={page === "review"}
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
          <button className="secondary theme-toggle" aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} onClick={() => setTheme(value => value === 'light' ? 'dark' : 'light')}>
            {theme === 'light' ? <Moon size={16}/> : <Sun size={16}/>}
          </button>
          <button className="text-button" onClick={inspect} disabled={!session}>
            <Radio size={14} />
            <span className={connected ? "dot online" : "dot"} />
            {needsInvite ? "Invitation required" : connected ? "Connected" : "Connecting"}
          </button>
        </header>
        <div className="workspace">
          <div className="production-header">
            <div>
              <h1>
                {session?.title || (needsInvite ? "Welcome to the studio." : "Setting the scene…")}{" "}
                {session && <span className="scene-chip">SCENE 01</span>}
              </h1>
            </div>
            <button
              className="secondary"
              aria-label="Scene settings"
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
                aria-pressed={page === "shoot"}
                disabled={!session}
                onClick={() => setPage("shoot")}
              >
                <Video size={15} />
                On set
              </button>
              <button
                className={page === "review" ? "selected" : ""}
                aria-pressed={page === "review"}
                disabled={!session}
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
              <div className="shoot-workspace">
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
                      {rolling && take?.decisions?.length ? (
                        <DecisionHud session={session} take={take} />
                      ) : null}
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
                              : session.state === "ARMED"
                                ? "Roll cameras or speak a direction when you're ready."
                              : "Arm the virtual cameras to begin your rehearsal."}
                          </p>
                        </div>
                      )}
                    </div>
                    <div className="program-caption">
                      <ShieldCheck size={14} />
                              <span>{session.source_set==='last-train-animatic-v1'?'Animatic originals preserved':session.source_set==='open-cafe-v1'?'Open-footage master preserved':'Fixture originals preserved'}</span>
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
                  <DirectionStudio session={session} busy={busy} transitioning={transitioning}
                    onCommand={(kind,options)=>command(kind,undefined,options)} onInspect={inspect}/>
                </div>
                <div className="studio-lower">
                  <div className="crew-dock">
                    <div className="section-label">
                      <span>
                        CAMERA CREW <small>3 virtual iPhones</small>
                      </span>
                      <span>Choose a view to cut</span>
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
                          holding={session.hold && session.selected_camera === cam.id}
                          rolling={rolling}
                        />
                      ))}
                    </div>
                  </div>
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
                  <div className="transport-next" aria-live="polite">
                    <strong>{rolling ? "Recording all three cameras" : session.state === "ARMED" ? "The crew is ready" : "Start your take"}</strong>
                    <span>{rolling ? "Switch cameras above. Every angle is still being saved." : session.state === "ARMED" ? "Press Roll cameras when the actors are ready." : "Arm the cameras, then roll when you are ready."}</span>
                  </div>
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
              </div>
            ) : (
              <Review
                session={session}
                onDirect={(note, takeId) => direct(note, "edit", takeId)}
                onCreateStyleLab={createStyleLab}
              />
            )
          ) : needsInvite ? (
            <div className="invite-layout">
            <div className="invite-scene">
              <img src={scenePlate} width="960" height="540" decoding="async" alt="Two performers in an openly licensed cafe scene" />
              <div className="invite-scene-copy"><Clapperboard size={25}/><h2>One take.<br/>Every point of view.</h2><p>Open live-action footage. Synchronized virtual camera views.</p></div>
            </div>
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
            </div>
          ) : (
            <div className="loading">
              {error?<button className="secondary" onClick={()=>location.reload()}>Retry connection</button>:<><LoaderCircle className="spin" /> Connecting to your production…</>}
            </div>
          )}
          <footer>
            <span>
              CLAPPY <i /> A SMALL CREW, A BIGGER PICTURE.
            </span>
            {session && <span>
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
            </span>}
          </footer>
        </div>
      </main>
      {session && page === "shoot" && (
        <div className={`director-assistant ${directorOpen ? "open" : ""}`}>
          {directorOpen && (
            <section className="director-popover" aria-label="Clappy director">
              <div className="director-popover-header">
                <span><Sparkles size={16}/><strong>Clappy director</strong></span>
                <button className="icon-button" onClick={() => setDirectorOpen(false)} aria-label="Close director">
                  <X size={17}/>
                </button>
              </div>
              <p className="director-popover-intro">Speak a direction or ask about this production.</p>
              <VoiceControl disabled={transitioning||busy} onAudio={voice}/>
              {session.queued_direction&&<div className="queued-direction" role="status"><strong>{session.queued_direction.status}</strong> {session.queued_direction.note} <span>Screenplay line {session.queued_direction.target_line_id+1}.</span></div>}
              <AgentNote session={session} compact onSend={(note) => direct(note, "recall")}/>
            </section>
          )}
          <button className="director-fab" onClick={() => setDirectorOpen(value => !value)}
            aria-label={directorOpen ? "Close Clappy director" : "Talk to Clappy director"}
            aria-expanded={directorOpen} title="Talk to Clappy director">
            <MessageCircle size={19}/><span>{directorOpen ? "Close" : "Ask Clappy"}</span>
          </button>
        </div>
      )}
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

function DecisionHud({session,take}:{session:Session;take:Take}) {
  const decision = take.decisions?.at(-1);
  if (!decision) return null;
  const source = decision.source === "gemini"
    ? "Clappy · Gemini"
    : decision.source === "queued-director"
      ? "Your direction"
      : decision.source === "safety-fallback"
        ? "Continuity safeguard"
        : decision.reason === "Opening shot"
          ? "Opening composition"
          : "You directed";
  const camera = session.cameras.find((item) => item.id === decision.camera);
  return <div className="decision-hud" key={`${decision.time}-${decision.camera}`} role="status" aria-live="polite">
    <span className="decision-signal"><Sparkles size={13}/>{source}</span>
    <strong>{camera?.role || `Camera ${decision.camera.toUpperCase()}`}</strong>
    <p>{decision.reason}</p>
    {session.live_direction ? <small>Following: {session.live_direction}</small> : null}
  </div>;
}

function Stream({ camera, path, frameRef, preview, sessionId }: { camera: Camera; sessionId:string; path?: string; preview?:string; frameRef?:React.RefObject<HTMLIFrameElement|null> }) {
  if(path&&camera.state!=='RECORDING')return <div className="empty-stream" role="status"><span>{camera.role} unavailable</span><small>Live connection interrupted</small></div>;
  if(!path&&preview)return <img className="source-preview" src={preview} alt={`${camera.role} - virtual camera preview`}/>;
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

function DirectionStudio({session,busy,transitioning,onCommand,onInspect}:{
  session:Session;
  busy:boolean;
  transitioning:boolean;
  onCommand:(kind:string,options?:{preset?:DirectingPreset;direction?:string})=>Promise<void>;
  onInspect:()=>Promise<void>;
}) {
  const [direction,setDirection]=useState(session.live_direction||"");
  useEffect(()=>setDirection(session.live_direction||""),[session.live_direction]);
  const active=directingPresets.find(item=>item.id===(session.directing_preset||"classic"))||directingPresets[0];
  const canUseAI=!!session.source_set&&session.source_set!=="charts";
  const fingerprint=directorFingerprint(session);
  return <section className="direction-studio" aria-label="Directing approach">
    <div className="direction-heading">
      <div className="direction-identity">
        <span className="clappy-orb"><Clapperboard size={18}/></span>
        <div><strong>Directing plan</strong><p>Decide who calls each shot before you roll.</p></div>
      </div>
    </div>
    <div className="direction-control">
      <span className="control-label">Who calls the shots?</span>
      <div className="direction-mode" aria-label="Direction mode">
        <button className={!session.auto_enabled?"selected":""} aria-pressed={!session.auto_enabled}
          disabled={busy||transitioning} onClick={()=>onCommand("auto_off")}><strong>You direct</strong><span>Cut live</span></button>
        <button className={session.auto_enabled?"selected":""} aria-pressed={!!session.auto_enabled}
          disabled={busy||transitioning||!canUseAI} title={!canUseAI?"Choose a dialogue source in Scene settings":""}
          onClick={()=>onCommand("auto_on")}><strong>Clappy directs</strong><span>Follows dialogue</span></button>
      </div>
      {!canUseAI && <p className="direction-help">Choose a dialogue scene in Scene settings to enable Clappy.</p>}
    </div>
    <div className="direction-control">
      <span className="control-label">Camera style</span>
      <div className="preset-list" aria-label="Camera-work preset">
      {directingPresets.map(item=><button key={item.id} className={item.id===active.id?"selected":""}
        aria-pressed={item.id===active.id} disabled={busy||transitioning}
        onClick={()=>onCommand("direct",{preset:item.id})}>
        <strong>{item.name}</strong><span>{item.short}</span>
      </button>)}
      </div>
      <p className="preset-description">{active.description}</p>
    </div>
    <form className="live-direction" onSubmit={async event=>{
      event.preventDefault();
      await onCommand("direct",{direction:direction.trim()});
    }}>
      <label htmlFor="live-direction">Add a direction <span>Optional</span></label>
      <input id="live-direction" value={direction} maxLength={300} minLength={3}
        onChange={event=>setDirection(event.target.value)}
        placeholder="Example: Favor Bella after the reveal"
        disabled={busy||transitioning}/>
      <button className="secondary" disabled={busy||transitioning||direction.trim().length<3}>Apply note</button>
    </form>
    <div className="direction-status">
      {session.live_direction&&<span className="active-note">Direction: {session.live_direction}</span>}
      <button className="text-button" onClick={onInspect}>Production log <ArrowRight size={14}/></button>
    </div>
    <div className={`director-fingerprint ${fingerprint ? "learned" : "learning"}`}>
      <Brain size={17}/>
      <div>
        <strong>Director fingerprint</strong>
        <span>{fingerprint?.summary || "Make two manual cuts and Clappy will begin learning your visual rhythm."}</span>
      </div>
      {fingerprint ? <button className="text-button" disabled={busy||transitioning}
        onClick={()=>onCommand("direct",{direction:fingerprint.instruction})}>Use my style <ArrowRight size={13}/></button> : <small>LEARNING</small>}
    </div>
  </section>;
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
  rolling,
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
  rolling: boolean;
  disabled: boolean;
}) {
  const stateLabel = camera.state === "RECORDING" ? "REC" : camera.state === "OFFLINE" ? "STANDBY" : camera.state;
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
            stateLabel
          )}
        </span>
      </div>
      <button
        className="camera-select"
        disabled={disabled}
        onClick={onSelect}
        aria-label={rolling ? `Cut to ${camera.role}` : `Preview ${camera.role}`}
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
              <span className="dot online" /> {rolling ? "ON PROGRAM" : "SELECTED"}
            </>
          ) : (
            <>
              <Wifi size={12} /> AVAILABLE
            </>
          )}
        </span>
        {rolling && <button disabled={disabled} onClick={onHold}>
            {holding ? "Release hold" : "Hold shot"}
            {holding ? <Check size={13} /> : <Focus size={13} />}
          </button>}
      </div>
    </article>
  );
}

function Review({
  session,
  onDirect,
  onCreateStyleLab,
}: {
  session: Session;
  onDirect: (note: string, takeId: string) => Promise<void>;
  onCreateStyleLab: (takeId: string, onProgress: (completed: number, total: number) => void) => Promise<void>;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const take =
    session.takes.find((t) => t.id === selected) || session.takes.at(-1);
  const [editId, setEditId] = useState<string | null>(null);
  const player = useRef<HTMLVideoElement|null>(null);
  const takeList = useRef<HTMLElement|null>(null);
  const resume = useRef({time:0,playing:false});
  const [labRunning,setLabRunning]=useState(false);
  const [labProgress,setLabProgress]=useState(0);
  const [labError,setLabError]=useState("");
  const edit = take?.edits.find((e) => e.id === editId) || take?.edits[0];
  const base = edit ? `/api/sessions/${session.id}/edits/${edit.id}` : "";
  const allocation=(version:Edit|undefined,camera:CameraId)=>version&&take?.duration?100*version.segments.filter(s=>s.camera===camera).reduce((n,s)=>n+s.end-s.start,0)/take.duration:0;
  useEffect(() => {
    const list = takeList.current;
    const selectedTake = list?.querySelector<HTMLElement>('button.selected');
    if (list && selectedTake && list.scrollWidth > list.clientWidth) {
      list.scrollLeft = selectedTake.offsetLeft - list.offsetLeft;
    }
  }, [take?.id]);
  useEffect(() => {
    if (session.agent?.status === "READY" && session.agent.edit_id) setEditId(session.agent.edit_id);
  }, [session.agent?.status, session.agent?.edit_id]);
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
      <aside className="take-list" ref={takeList} aria-label="Saved takes">
        <div className="eyebrow">YOUR TAKES</div>
        {session.takes.map((t) => (
          <button
            key={t.id}
            className={t.id === take.id ? "selected" : ""}
            aria-pressed={t.id === take.id}
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
        <div className="cut-lab" aria-label="Director's Cut Lab">
          <div className="cut-lab-intro">
            <span className="clappy-orb"><Sparkles size={17}/></span>
            <div><strong>One performance. Three films.</strong><p>Compare how directing intent changes the exact same source footage.</p></div>
          </div>
          <div className="cut-versions">
            <button className={edit?.id===take.edits[0]?.id?"selected":""} onClick={()=>setEditId(take.edits[0]?.id || null)}>
              <span>01</span><strong>Live cut</strong><small>As directed on set</small>
            </button>
            {styleLabBriefs.map((style,index)=>{
              const version=take.edits.find(item=>item.brief?.includes(`[STYLE LAB: ${style.id}]`));
              return <button key={style.id} disabled={!version} className={version?.id===edit?.id?"selected":""}
                onClick={()=>version&&setEditId(version.id)}>
                <span>0{index+2}</span><strong>{style.name}</strong><small>{version ? version.status === "READY" ? "Ready to compare" : "Rendering film" : labRunning ? "Clappy is directing" : "Awaiting interpretation"}</small>
              </button>;
            })}
          </div>
          <div className="cut-lab-action">
            <span>{labError || (labRunning ? `Creating interpretation ${Math.min(labProgress+1,styleLabBriefs.length)} of ${styleLabBriefs.length}…` : take.edits.filter(item=>item.brief?.includes("[STYLE LAB:")).length >= styleLabBriefs.length ? "All three interpretations use the same preserved originals." : "Gemini directs two alternate versions from the preserved originals.")}</span>
            <button className="primary" disabled={labRunning||take.edits.filter(item=>item.brief?.includes("[STYLE LAB:")).length>=styleLabBriefs.length}
              onClick={async()=>{setLabRunning(true);setLabError("");setLabProgress(0);try{await onCreateStyleLab(take.id,(done)=>setLabProgress(done));}catch(exc){setLabError((exc as Error).message);}finally{setLabRunning(false);}}}>
              {labRunning?<LoaderCircle size={15} className="spin"/>:<Sparkles size={15}/>} {labRunning?"Directing…":"Create three cuts"}
            </button>
          </div>
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
                  title={`${seg.camera.toUpperCase()} · ${clock(seg.start)}-${clock(seg.end)}`}
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
            <div className="edit-rationale">
              <Sparkles size={15}/><strong>Why this cut</strong><span>{edit.explanation || edit.segments[0]?.reason}</span>
            </div>
            <div className="edit-actions">
              <div>
                {take.edits.map((e) => (
                  <button
                    className={
                      e.id === edit.id ? "secondary selected" : "secondary"
                    }
                    key={e.id}
                    aria-pressed={e.id === edit.id}
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
  compact = false,
  onSend,
}: {
  session: Session;
  editing?: boolean;
  compact?: boolean;
  onSend: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const thinking = sending || session.agent?.status === "THINKING";
  return (
    <section className="agent-note">
      {!compact && <div className="agent-note-title">
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
      </div>}
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
            {sources.includes('open-cafe-v1')&&<option value="open-cafe-v1">The letter · live-action café rehearsal (derived views)</option>}
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
