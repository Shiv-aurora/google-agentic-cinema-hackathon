"""Render three explicitly derived animatic views from one Google-generated plate."""
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ass_time(seconds):
    centiseconds=round(seconds*100)
    return f"{centiseconds//360000}:{centiseconds//6000%60:02d}:{centiseconds//100%60:02d}.{centiseconds%100:02d}"


def main():
    root=Path("data/scenes/last-train-animatic-v1")
    root.mkdir(parents=True,exist_ok=True)
    plate=Path("assets/demo/last-train-v1/scene-plate.png")
    audio_root=Path("data/scenes/last-train-v1")
    audio=json.loads((audio_root/"audio-manifest.json").read_text())
    assert digest(audio_root/"master.wav")==audio["sha256"]
    provenance=json.loads(plate.with_name("provenance.json").read_text())
    assert digest(plate)==provenance["sha256"]
    subtitles=root/"dialogue.ass"
    header="""[Script Info]
ScriptType: v4.00+
PlayResX: 960
PlayResY: 540
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Dialogue,Arial,19,&H00F0F4F0,&H000000FF,&HCC000000,&H90000000,0,0,0,0,100,100,0,0,1,1.2,0,2,40,40,35,1
Style: Disclosure,Arial,10,&H00C8D8CC,&H000000FF,&H80000000,&H90000000,0,0,0,0,100,100,1,0,1,1,0,7,20,20,12,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.00,0:01:00.00,Disclosure,,0,0,0,,AI STILL-FRAME ANIMATIC  /  GOOGLE VOICES  /  DERIVED VIEWS
"""
    lines=[]
    for cue in audio["evaluation_only_ground_truth"]:
        text=cue["text"].replace("{","").replace("}","").replace("\n"," ")
        lines.append(f"Dialogue: 1,{ass_time(cue['start'])},{ass_time(cue['end']+.4)},Dialogue,,0,0,0,,{text}")
    subtitles.write_text(header+"\n".join(lines)+"\n")
    # Rectangles selected after visually inspecting the generated 2752×1536 plate.
    rectangles={"a":(1376,774,60,140),"b":(1376,774,1316,210),"c":(2730,1536,11,0)}
    cameras=[]
    for camera,rect in rectangles.items():
        output=root/f"camera-{camera}.mp4"
        if not output.exists():
            crop=":".join(map(str,rect))
            filters=(f"crop={crop},scale=2880:1620,zoompan=z='1.025+0.018*sin(on/600)':"
                "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=30:s=960x540:fps=30,"
                f"setsar=1,subtitles={subtitles.as_posix()}")
            subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-n","-loop","1","-framerate","1","-i",str(plate),
                "-i",str(audio_root/"master.wav"),"-map","0:v:0","-map","1:a:0","-vf",filters,"-t","60",
                "-c:v","libx264","-preset","fast","-crf","21","-profile:v","baseline","-pix_fmt","yuv420p","-bf","0","-g","30",
                "-c:a","aac","-b:a","160k","-movflags","+faststart",str(output)],check=True)
        thumb=root/f"camera-{camera}.jpg"
        if not thumb.exists():
            subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-n","-i",str(output),"-frames:v","1","-q:v","3",str(thumb)],check=True)
        cameras.append({"id":camera,"file":output.name,"duration":60,"sha256":digest(output),"derived_crop":list(rect),
                        "source_clock":{"epoch":"last-train-animatic-v1","offset_seconds":0}})
        print(f"Verified animatic camera {camera.upper()}",flush=True)
    manifest={"kind":"google-still-frame-animatic","duration":60,"fps":30,"cameras":cameras,
        "description":"Three derived crops of one Google-generated still plate, slow camera moves and Google-voiced dialogue. Not independent live-action angles or lip-synced video.",
        "image_sha256":provenance["sha256"],"image_model":provenance["model"],"audio_sha256":audio["sha256"]}
    path=root/"manifest.json"
    if path.exists():
        assert json.loads(path.read_text())==manifest,"Create a new version instead of replacing source media"
    else:
        path.write_text(json.dumps(manifest,indent=2)+"\n")


if __name__=="__main__":
    main()
