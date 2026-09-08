"""Google speech recognizes PCM actually received from a source or director mic."""
import asyncio
import time

from google.cloud import speech_v1 as speech

from services.api.config import google_credentials


async def recognize_stream(chunks, on_result, *, sample_rate=16000, language="en-US"):
    client = speech.SpeechAsyncClient(credentials=google_credentials())
    async def requests():
        yield speech.StreamingRecognizeRequest(streaming_config=speech.StreamingRecognitionConfig(
            config=speech.RecognitionConfig(encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=sample_rate, language_code=language, enable_automatic_punctuation=True,
                enable_word_time_offsets=True, model="latest_long"), interim_results=True))
        async for chunk in chunks:
            yield speech.StreamingRecognizeRequest(audio_content=chunk)
    try:
        responses = await client.streaming_recognize(requests=requests(), timeout=75)
        async for response in responses:
            for result in response.results:
                if not result.alternatives:
                    continue
                alternative = result.alternatives[0]
                await on_result({"text": alternative.transcript, "final": result.is_final,
                    "confidence": alternative.confidence, "stability": result.stability,
                    "audio_end": result.result_end_time.total_seconds(), "received_at": time.time(),
                    "words": [{"text": word.word, "start": word.start_time.total_seconds(), "end": word.end_time.total_seconds()} for word in alternative.words]})
    finally:
        await client.transport.close()


async def ffmpeg_pcm(source, *, realtime=False):
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
    if realtime:
        args += ["-re"]
    if source.startswith("rtsp://"):
        args += ["-rtsp_transport", "tcp"]
    proc = await asyncio.create_subprocess_exec(*args, "-i", source, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        while chunk := await proc.stdout.read(3200):
            yield chunk
        await proc.wait()
        if proc.returncode:
            raise RuntimeError("Performance audio decoder exited unexpectedly")
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
