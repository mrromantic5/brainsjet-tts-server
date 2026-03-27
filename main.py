import os
import io
import json
import tempfile
import httpx
import edge_tts
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Voice map (friendly name → Edge TTS voice ID) ──
VOICES = {
    "lisa":    "en-US-AriaNeural",
    "jenny":   "en-US-JennyNeural",
    "michelle":"en-US-MichelleNeural",
    "monica":  "en-US-MonicaNeural",
    "elizabeth":"en-US-ElizabethNeural",
    "ana":     "en-US-AnaNeural",
    "guy":     "en-US-GuyNeural",
    "davis":   "en-US-DavisNeural",
    "jason":   "en-US-JasonNeural",
    "roger":   "en-US-RogerNeural",
    "sonia":   "en-GB-SoniaNeural",
    "libby":   "en-GB-LibbyNeural",
    "ryan":    "en-GB-RyanNeural",
    "natasha": "en-AU-NatashaNeural",
    "william": "en-AU-WilliamNeural",
}


async def generate_tts(text: str, voice_id: str):
    """Generate TTS audio and collect word timings via edge-tts."""
    communicate = edge_tts.Communicate(text, voice_id)
    audio_chunks = []
    words = []
    char_offset = 0

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word_text = chunk["text"]
            start_char = chunk.get("offset", char_offset)
            end_char = start_char + len(word_text)
            start_ms = chunk.get("offset", 0) // 10000   # 100ns → ms
            duration_ms = chunk.get("duration", 0) // 10000
            words.append({
                "type": "word",
                "value": word_text,
                "start": start_char,
                "end": end_char,
                "startTime": start_ms,
                "endTime": start_ms + duration_ms,
            })
            char_offset = end_char + 1

    audio_bytes = b"".join(audio_chunks)
    return audio_bytes, words


async def upload_to_tmpfiles(audio_bytes: bytes) -> str:
    """Upload MP3 bytes to tmpfiles.org and return the direct download URL."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": ("audio.mp3", audio_bytes, "audio/mpeg")},
        )
        data = response.json()
        # tmpfiles returns: {"status":"success","data":{"url":"https://tmpfiles.org/XXXXXX/audio.mp3"}}
        raw_url = data["data"]["url"]
        # Convert to direct download URL
        dl_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        return dl_url


def build_transcript(text: str, words: list) -> dict:
    """Build transcript object matching friend's API format."""
    start_time = words[0]["startTime"] if words else 0
    end_time = words[-1]["endTime"] if words else 0
    return {
        "type": "sentence",
        "value": text,
        "start": 0,
        "end": len(text),
        "startTime": start_time,
        "endTime": end_time,
        "chunks": words,
    }


@app.get("/")
async def root():
    return {
        "name": "BRAINS JET AI TTS",
        "creator": "MR.ROMANTIC",
        "usage": "/?q=Hello World&voicename=lisa",
        "voices": list(VOICES.keys()),
    }


@app.get("/tts")
@app.get("/api/tts")
async def tts(
    q: str = Query(..., description="Text to speak"),
    voicename: str = Query("lisa", description="Voice name"),
):
    voice_key = voicename.lower().strip()
    voice_id = VOICES.get(voice_key, "en-US-AriaNeural")

    try:
        audio_bytes, words = await generate_tts(q, voice_id)

        if not audio_bytes:
            return JSONResponse({"error": "TTS generation failed"}, status_code=500)

        mp3_url = await upload_to_tmpfiles(audio_bytes)
        transcript = build_transcript(q, words)

        return JSONResponse({
            "url": mp3_url,
            "transcript": transcript,
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Root path also accepts ?q= like friend's API
@app.get("/tts-root")
async def tts_root_alias(
    q: str = Query(None),
    voicename: str = Query("lisa"),
):
    if not q:
        return root()
    return await tts(q=q, voicename=voicename)
