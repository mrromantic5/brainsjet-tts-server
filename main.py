import base64
import edge_tts
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="BrainsJet TTS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICES = {
    # US Female
    "lisa":       "en-US-AriaNeural",
    "jane":       "en-US-JaneNeural",
    "jenny":      "en-US-JennyNeural",
    "nancy":      "en-US-NancyNeural",
    "amber":      "en-US-AmberNeural",
    "sara":       "en-US-SaraNeural",
    "michelle":   "en-US-MichelleNeural",
    "monica":     "en-US-MonicaNeural",
    "elizabeth":  "en-US-ElizabethNeural",
    "ana":        "en-US-AnaNeural",
    # US Male
    "guy":        "en-US-GuyNeural",
    "tony":       "en-US-TonyNeural",
    "davis":      "en-US-DavisNeural",
    "jason":      "en-US-JasonNeural",
    "roger":      "en-US-RogerNeural",
    "eric":       "en-US-EricNeural",
    "brandon":    "en-US-BrandonNeural",
    "christopher":"en-US-ChristopherNeural",
    # UK
    "sonia":      "en-GB-SoniaNeural",
    "libby":      "en-GB-LibbyNeural",
    "mia":        "en-GB-MiaNeural",
    "ryan":       "en-GB-RyanNeural",
    # AU
    "natasha":    "en-AU-NatashaNeural",
    "william":    "en-AU-WilliamNeural",
}


async def generate_tts(text: str, voice_id: str):
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
            start_ms = chunk.get("offset", 0) // 10000
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

    return b"".join(audio_chunks), words


def build_transcript(text: str, words: list) -> dict:
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


async def _tts_handler(q: str, voicename: str):
    voice_id = VOICES.get(voicename.lower().strip(), "en-US-AriaNeural")
    audio_bytes, words = await generate_tts(q, voice_id)

    if not audio_bytes:
        return JSONResponse({"error": "TTS generation produced no audio"}, status_code=500)

    # Return audio as base64 data URL — no external upload needed
    b64 = base64.b64encode(audio_bytes).decode("utf-8")
    audio_url = f"data:audio/mpeg;base64,{b64}"

    return JSONResponse({
        "url": audio_url,
        "transcript": build_transcript(q, words),
    })


@app.api_route("/", methods=["GET", "HEAD"])
async def root(q: str = Query(None), voicename: str = Query("lisa")):
    if not q:
        return JSONResponse({
            "name": "BrainsJet TTS API",
            "creator": "MR.ROMANTIC",
            "usage": "/?q=Hello World&voicename=lisa",
            "voices": list(VOICES.keys()),
        })
    try:
        return await _tts_handler(q, voicename)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/tts")
@app.get("/api/tts")
async def tts(q: str = Query(...), voicename: str = Query("lisa")):
    try:
        return await _tts_handler(q, voicename)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return JSONResponse({"status": "ok", "voices": len(VOICES)})
