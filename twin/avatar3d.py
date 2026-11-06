"""Real 3D talking avatar: a rigged GLB (made from a selfie at avaturn.me) rendered with
three.js + the TalkingHead library (real-time lip-sync, blinking, head/hand motion).
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

TEMPLATE = Path(__file__).with_name("avatar3d.html")

CDN = {
    "three": "https://cdn.jsdelivr.net/npm/three@0.186/build/three.module.js/+esm",
    "three_addons": "https://cdn.jsdelivr.net/npm/three@0.186/examples/jsm/",
    "talkinghead": "https://cdn.jsdelivr.net/gh/met4citizen/TalkingHead@1.8/modules/talkinghead.mjs",
}

# Small bone/eyelid tweaks the TalkingHead author recommends for Avaturn (T2) avatars.
AVATURN_RETARGET = {
    "Hips": {"y": 0.03}, "Spine": {"y": 0.02}, "Spine1": {"y": 0.02, "z": 0.01},
    "Spine2": {"y": 0.02, "z": 0.01}, "Neck": {"z": 0.02, "y": 0.01}, "Head": {"z": 0.02},
    "LeftShoulder": {"rx": -0.5}, "RightShoulder": {"rx": -0.5},
    "scaleToHipsLevel": 1.0,
}
AVATURN_BASELINE = {"headRotateX": -0.05, "eyeBlinkLeft": 0.15, "eyeBlinkRight": 0.15}


def build_html(
    audio_mp3: bytes | None = None,
    text: str | None = None,
    words: list[str] | None = None,
    wtimes: list[float] | None = None,
    wdurations: list[float] | None = None,
    lang: str = "en",
    poster: str | Path | None = None,
    glb_urls: list[str] | None = None,
    body: str = "M",
    imports: dict | None = None,
    force_play: bool = False,
) -> str:
    env_imports = json.loads(os.environ.get("TWIN_IMPORTS_JSON", "{}"))  # offline dev override
    imap = {**CDN, **env_imports, **(imports or {})}
    cfg = {
        "audio": base64.b64encode(audio_mp3).decode() if audio_mp3 else None,
        "text": text,
        "words": words or [],
        "wtimes": wtimes or [],
        "wdurations": wdurations or [],
        "lang": {"en": "en-IN", "te": "te-IN"}.get(lang, "en-IN"),
        "poster": (f"data:image/jpeg;base64,{base64.b64encode(Path(poster).read_bytes()).decode()}"
                   if poster and Path(poster).exists() else None),
        "glbUrls": glb_urls or [],
        "body": body,
        "retarget": AVATURN_RETARGET,
        "baseline": AVATURN_BASELINE,
        "forcePlay": force_play,
        "view": "upper",
    }
    payload = json.dumps(cfg).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    return (html.replace("__THREE_ADDONS__", imap["three_addons"])
                .replace("__THREE__", imap["three"])
                .replace("__TALKINGHEAD__", imap["talkinghead"])
                .replace("__CONFIG__", payload))
