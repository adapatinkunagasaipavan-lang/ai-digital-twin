"""Optional 'realistic' mode: photo + text -> talking-head video via the D-ID API.

Needs a D-ID API key (https://studio.d-id.com/account-settings). Docs:
https://docs.d-id.com/reference/talks
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

BASE = "https://api.d-id.com"

VOICE_IDS = {"en": "en-IN-PrabhatNeural", "te": "te-IN-MohanNeural"}


class DIDError(RuntimeError):
    pass


def _headers(api_key: str) -> dict:
    # D-ID keys are already in "user:secret" base64 form.
    return {"Authorization": f"Basic {api_key}", "accept": "application/json"}


def upload_image(api_key: str, image_path: str | Path) -> str:
    with open(image_path, "rb") as f:
        r = requests.post(f"{BASE}/images", headers=_headers(api_key),
                          files={"image": (Path(image_path).name, f, "image/jpeg")}, timeout=60)
    if r.status_code >= 400:
        raise DIDError(f"image upload failed: {r.status_code} {r.text[:200]}")
    return r.json()["url"]


def create_talk(api_key: str, image_url: str, text: str, lang: str = "en",
                poll_seconds: float = 2.0, timeout: float = 120.0) -> str:
    """Create a talking video and return its result URL."""
    body = {
        "source_url": image_url,
        "script": {
            "type": "text",
            "input": text[:3000],
            "provider": {"type": "microsoft", "voice_id": VOICE_IDS.get(lang, VOICE_IDS["en"])},
        },
        "config": {"fluent": True, "pad_audio": 0.0},
    }
    r = requests.post(f"{BASE}/talks", headers={**_headers(api_key), "content-type": "application/json"},
                      json=body, timeout=60)
    if r.status_code >= 400:
        raise DIDError(f"create talk failed: {r.status_code} {r.text[:200]}")
    talk_id = r.json()["id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        s = requests.get(f"{BASE}/talks/{talk_id}", headers=_headers(api_key), timeout=30)
        if s.status_code >= 400:
            raise DIDError(f"poll failed: {s.status_code} {s.text[:200]}")
        data = s.json()
        status = data.get("status")
        if status == "done":
            return data["result_url"]
        if status in ("error", "rejected"):
            raise DIDError(f"D-ID reported {status}: {data.get('error') or data}")
        time.sleep(poll_seconds)
    raise DIDError("timed out waiting for the video")
