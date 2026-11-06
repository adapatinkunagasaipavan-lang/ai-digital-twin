"""Text-to-speech (edge-tts, free) and speech-to-text (Google web speech, free)."""
from __future__ import annotations

import asyncio
import io
import re

VOICES = {
    "en": "en-IN-PrabhatNeural",   # Indian English, male
    "te": "te-IN-MohanNeural",     # Telugu, male
}
STT_LANG = {"en": "en-IN", "te": "te-IN"}


def speakable(text: str) -> str:
    """Strip markdown/URLs so the voice doesn't read symbols."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


async def _synth(text: str, voice: str) -> bytes:
    import edge_tts

    chunks = []
    async for ch in edge_tts.Communicate(text, voice).stream():
        if ch["type"] == "audio":
            chunks.append(ch["data"])
    return b"".join(chunks)


async def _synth_timed(text: str, voice: str):
    import edge_tts

    try:
        comm = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    except TypeError:  # older edge-tts: word boundaries are the default
        comm = edge_tts.Communicate(text, voice)
    chunks, words, wtimes, wdur = [], [], [], []
    async for ch in comm.stream():
        if ch["type"] == "audio":
            chunks.append(ch["data"])
        elif ch["type"] == "WordBoundary":
            words.append(ch["text"])
            wtimes.append(ch["offset"] / 10_000)      # 100 ns ticks -> ms
            wdur.append(ch["duration"] / 10_000)
    return b"".join(chunks), words, wtimes, wdur


def tts_timed(text: str, lang: str = "en", timeout: float = 25.0):
    """Return (mp3_bytes, words, wtimes_ms, wdurations_ms) or None if unreachable.

    Word timings may be empty (some voices only give sentence marks); the 3D
    avatar then spreads the words over the clip itself.
    """
    text = speakable(text)
    if not text:
        return None
    voice = VOICES.get(lang, VOICES["en"])
    try:
        audio, w, t, d = asyncio.run(asyncio.wait_for(_synth_timed(text, voice), timeout))
        return (audio, w, t, d) if audio else None
    except Exception:
        return None


def tts_mp3(text: str, lang: str = "en", timeout: float = 20.0) -> bytes | None:
    """Return MP3 bytes, or None if the service is unreachable."""
    text = speakable(text)
    if not text:
        return None
    voice = VOICES.get(lang, VOICES["en"])
    try:
        return asyncio.run(asyncio.wait_for(_synth(text, voice), timeout)) or None
    except Exception:
        return None


def transcribe(wav_bytes: bytes, lang: str = "en") -> str | None:
    """Transcribe WAV bytes. Returns None if nothing was recognised."""
    try:
        import speech_recognition as sr

        r = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(wav_bytes)) as src:
            audio = r.record(src)
        return r.recognize_google(audio, language=STT_LANG.get(lang, "en-IN")) or None
    except Exception:
        return None
