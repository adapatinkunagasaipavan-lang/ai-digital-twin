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
