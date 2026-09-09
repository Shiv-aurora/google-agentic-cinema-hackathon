export type CameraId = "a" | "b" | "c";
export type DirectingPreset = "classic" | "reaction" | "patient" | "tension";
export type Camera = {
  id: CameraId;
  name: string;
  role: string;
  framing: string;
  color: string;
  state: string;
};
export type Edit = {
  id: string;
  name: string;
  brief?: string;
  explanation?: string;
  status: string;
  error?: string;
  sync: string;
  manifest_available?: boolean;
  segments: { camera: CameraId; start: number; end: number; reason: string }[];
};
export type Take = {
  id: string;
  number: number;
  state: string;
  started_at?: number;
  clock_epoch?: string;
  source_tag?: string;
  duration?: number;
  paths?: Record<CameraId, string>;
  decisions?: { camera: CameraId; time: number; reason: string; source?: string; line_event_id?: number }[];
  edits: Edit[];
  recordings_verified?: boolean;
  recordings?: Record<
    string,
    { file: string; duration: number; bytes: number }[]
  >;
};
export type Session = {
  id: string;
  title: string;
  scene: string;
  script: string;
  state: string;
  revision: number;
  cameras: Camera[];
  takes: Take[];
  active_take: string | null;
  selected_camera: CameraId;
  hold: boolean;
  note: string;
  error: string | null;
  policy: string;
  agent?: { status: string; message: string; edit_id?: string };
  source_set?: "charts" | "last-train-v1" | "last-train-animatic-v1";
  auto_enabled?: boolean;
  directing_preset?: DirectingPreset;
  live_direction?: string;
  direction_epoch?: number;
  queued_direction?: {status:string; character:string; camera:CameraId; target_line_id:number; note:string};
  performance?: { status: string; text: string; line?: {id:number; character:string; confidence:number} };
};
export type Health = {
  media: { ready: boolean; error?: string };
  fixtures: boolean;
  ai: { ready: boolean; reason: string };
  memory: { ready: boolean; reason: string };
  sources?: string[];
};
