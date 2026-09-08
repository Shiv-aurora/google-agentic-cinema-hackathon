import { useEffect, useRef, useState } from 'react';
import { Mic, Square, LoaderCircle } from 'lucide-react';

export function VoiceControl({disabled,onAudio}:{disabled:boolean;onAudio:(audio:Blob)=>Promise<string>}){
  const [recording,setRecording]=useState(false);
  const [sending,setSending]=useState(false);
  const [starting,setStarting]=useState(false);
  const [message,setMessage]=useState('Director microphone only · sent to Google when you stop.');
  const recorder=useRef<MediaRecorder|null>(null);
  const stream=useRef<MediaStream|null>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{
    mounted.current=false;clearTimeout(timer.current);
    if(recorder.current){recorder.current.onstop=null;if(recorder.current.state!=='inactive')recorder.current.stop();}
    stream.current?.getTracks().forEach(track=>track.stop());
  };},[]);
  const toggle=async()=>{
    if(recording){recorder.current?.stop();return;}
    setStarting(true);
    try{
      if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('Microphone recording needs HTTPS or localhost and a supported browser.');
      stream.current=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
      if(!mounted.current){stream.current.getTracks().forEach(track=>track.stop());return;}
      const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type));
      const active=new MediaRecorder(stream.current,mime?{mimeType:mime}:undefined);
      recorder.current=active;const parts:Blob[]=[];
      active.ondataavailable=event=>{if(event.data.size)parts.push(event.data);};
      active.onerror=()=>{setMessage('Microphone recording failed. Please retry.');active.stop();};
      active.onstop=async()=>{
        clearTimeout(timer.current);stream.current?.getTracks().forEach(track=>track.stop());setRecording(false);setSending(true);
        try{const transcript=await onAudio(new Blob(parts,{type:active.mimeType}));if(mounted.current)setMessage(`Heard: “${transcript}”`);}
        catch(exc){if(mounted.current)setMessage((exc as Error).message);}
        finally{if(mounted.current)setSending(false);}
      };
      active.start();setRecording(true);setMessage('Listening to your direction… tap Send direction when done.');
      timer.current=setTimeout(()=>{if(active.state!=='inactive')active.stop();},10000);
    }catch(exc){stream.current?.getTracks().forEach(track=>track.stop());if(mounted.current){setRecording(false);setMessage((exc as Error).message);}}
    finally{if(mounted.current)setStarting(false);}
  };
  return <div className="voice-control"><button className={recording?'secondary listening':'secondary'} onClick={toggle} disabled={starting||sending||(!recording&&disabled)}>
    {sending?<LoaderCircle size={15} className="spin"/>:recording?<Square size={15}/>:<Mic size={15}/>}
    {starting?'Opening microphone…':sending?'Recognizing direction…':recording?'Send direction':'Speak a direction'}</button><span role="status">{message}</span></div>;
}
