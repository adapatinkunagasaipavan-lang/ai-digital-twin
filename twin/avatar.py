"""Builds the HTML/JS component that animates the photo (lip-sync, blink, head sway)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("avatar.html")

# Face landmarks as fractions of photo width/height (tuned for assets/photo.jpg).
DEFAULT_LANDMARKS = {
    "mouth": [0.468, 0.378],     # centre of the lip line
    "mouthW": 0.150,             # lip width
    "chin": 0.475,               # bottom of the jaw strip that moves
    "jawL": 0.315, "jawR": 0.605,
    "eyeL": [0.380, 0.293],      # viewer's left eye
    "eyeR": [0.514, 0.274],
    "eyeRx": 0.034, "eyeRy": 0.012, "eyeTilt": -0.17,
    "neck": [0.47, 0.62],        # pivot for head sway
}


def _data_uri(path: str | Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def build_html(
    photo_path: str | Path,
    audio_mp3: bytes | None = None,
    text: str | None = None,
    lang: str = "en",
    landmarks: dict | None = None,
    debug: bool = False,
) -> str:
    """Return the avatar HTML.

    audio_mp3: if given, the avatar plays it and lip-syncs to its loudness.
    text:      if given WITHOUT audio, the browser's built-in voice speaks it.
    """
    lm = {**DEFAULT_LANDMARKS, **(landmarks or {})}
    mesh_file = Path(photo_path).with_name("face_mesh.json")
    mesh = json.loads(mesh_file.read_text()) if mesh_file.exists() else None
    cfg = {
        "mesh": mesh,
        "photo": _data_uri(photo_path, "image/jpeg"),
        "audio": base64.b64encode(audio_mp3).decode() if audio_mp3 else None,
        "text": text if (text and not audio_mp3) else None,
        "lang": {"en": "en-IN", "te": "te-IN"}.get(lang, "en-IN"),
        "landmarks": lm,
        "debug": debug,
    }
    payload = json.dumps(cfg).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("__CONFIG__", payload)
