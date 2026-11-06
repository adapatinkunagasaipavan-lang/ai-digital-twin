"""AI Digital Twin - talk to an AI version of me (Streamlit app).

Run:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from twin import did_client, voice
from twin.avatar import build_html
from twin.avatar3d import build_html as build_html_3d
from twin.brain import Brain, has_placeholders, load_profile

ROOT = Path(__file__).parent
PHOTO = ROOT / "assets" / "photo.jpg"
PROFILE = ROOT / "profile.yaml"
GLB = ROOT / "static" / "avatar.glb"   # rigged 3D avatar made at avaturn.me (see README)
GLB_FALLBACK_URLS = [
    os.environ.get("AVATAR_GLB_URL") or
    "https://raw.githubusercontent.com/adapatinkunagasaipavan-lang/ai-digital-twin/main/static/avatar.glb",
]

st.set_page_config(page_title="AI Digital Twin", page_icon="🧑‍💻", layout="wide")


# ------------------------------------------------------------------ helpers
def secret(name: str) -> str | None:
    """Read a key from Streamlit secrets, then environment variables."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets.toml present
        pass
    return os.environ.get(name)


@st.cache_data
def get_profile(mtime: float) -> dict:
    return load_profile(PROFILE)


profile = get_profile(PROFILE.stat().st_mtime)
name = profile.get("name", "Me")

ss = st.session_state
ss.setdefault("messages", [])
ss.setdefault("play", None)       # what the avatar should say on the next render
ss.setdefault("video_url", None)  # D-ID result
ss.setdefault("mic_n", 0)
ss.setdefault("seen_audio", "")
ss.setdefault("did_image_url", None)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    lang_label = st.radio("Language", ["English", "తెలుగు (Telugu)"], horizontal=True)
    lang = "te" if lang_label.startswith("తెలుగు") else "en"
    voice_on = st.toggle("Voice replies", value=True)

    MODES = ["Real 3D avatar (free, live)", "Animated photo (2.5D)", "Realistic video (D-ID)"]
    mode = st.radio(
        "Avatar mode", MODES, index=0 if GLB.exists() else 1,
        help="Real 3D needs static/avatar.glb (made from your selfie at avaturn.me). "
             "D-ID needs an API key and credits.",
    )
    if mode == MODES[0] and not GLB.exists():
        st.warning("static/avatar.glb not found yet. Create it at avaturn.me and add it to the repo.")

    with st.expander("🔑 API keys (optional)"):
        st.caption("Stored only in this browser session. For permanent keys use "
                   "`.env` locally or Streamlit secrets when deployed.")
        k_anthropic = st.text_input("Anthropic API key", type="password") or secret("ANTHROPIC_API_KEY")
        k_did = st.text_input("D-ID API key", type="password") or secret("DID_API_KEY")

    if st.button("🗑️ Clear conversation"):
        ss.messages, ss.play, ss.video_url = [], None, None
        st.rerun()

    brain = Brain(profile, api_key=k_anthropic)
    st.caption("🧠 Brain: **Claude API**" if brain.uses_llm else "🧠 Brain: **offline mode** (add an Anthropic key for full answers)")

# ------------------------------------------------------------------ header
st.title(f"🧑‍💻 Hi, I'm {name}'s AI twin")
st.caption(profile.get("headline", ""))
if has_placeholders(profile):
    st.warning("`profile.yaml` still has placeholders like `[Your role]`. Edit it so I answer with your real details.")

avatar_col, chat_col = st.columns([5, 6], gap="large")


# ------------------------------------------------------------------ logic
def answer(prompt: str) -> None:
    history = list(ss.messages)
    ss.messages.append({"role": "user", "content": prompt})
    with st.spinner("Thinking…"):
        text, src = brain.reply(history, prompt, lang)
    ss.messages.append({"role": "assistant", "content": text, "src": src})

    ss.play, ss.video_url = {"text": text, "audio": None}, None
    if mode.startswith("Realistic"):
        if not k_did:
            st.toast("Add a D-ID API key in the sidebar for realistic mode. Using the 3D photo avatar.", icon="⚠️")
        else:
            try:
                with st.spinner("Rendering video…"):
                    if not ss.did_image_url:
                        ss.did_image_url = did_client.upload_image(k_did, PHOTO)
                    ss.video_url = did_client.create_talk(k_did, ss.did_image_url, text, lang)
                ss.play = None
                return
            except Exception as exc:
                st.toast(f"D-ID failed ({exc}). Using the 3D photo avatar.", icon="⚠️")
    if voice_on:
        if mode.startswith("Real 3D"):
            timed = voice.tts_timed(text, lang)
            if timed:
                ss.play.update(audio=timed[0], words=timed[1], wtimes=timed[2], wdurations=timed[3])
        else:
            ss.play["audio"] = voice.tts_mp3(text, lang)


SUGGESTIONS = ["Tell me about yourself", "What projects have you built?",
               "What are your strengths?", "Why should we hire you?"]

queued = None
with chat_col:
    st.subheader("💬 Ask me anything")
    cols = st.columns(2)
    for i, s in enumerate(SUGGESTIONS):
        if cols[i % 2].button(s, use_container_width=True, key=f"sug{i}"):
            queued = s

    if hasattr(st, "audio_input"):
        clip = st.audio_input("🎤 Or ask by voice", key=f"mic_{ss.mic_n}")
        if clip is not None:
            data = clip.getvalue()
            digest = hashlib.md5(data).hexdigest()
            if digest != ss.seen_audio:
                ss.seen_audio = digest
                with st.spinner("Listening…"):
                    heard = voice.transcribe(data, lang)
                if heard:
                    queued = heard
                    ss.mic_n += 1   # fresh recorder next time
                else:
                    st.toast("Could not understand the audio. Please try again.", icon="🎤")

typed = st.chat_input("Type your question…")
prompt = typed or queued
if prompt:
    answer(prompt)

# ------------------------------------------------------------------ avatar
with avatar_col:
    play, ss.play = ss.play, None  # speak once, then go idle on later reruns
    if ss.video_url:
        st.video(ss.video_url, autoplay=True)
    elif mode.startswith("Real 3D") and GLB.exists():
        p = play or {}
        components.html(build_html_3d(
            audio_mp3=p.get("audio") if voice_on else None,
            text=p.get("text"), words=p.get("words"), wtimes=p.get("wtimes"),
            wdurations=p.get("wdurations"), lang=lang, poster=PHOTO,
            glb_urls=GLB_FALLBACK_URLS, body="M",
            preset=profile.get("avatar_preset", "avatarsdk"),
        ), height=540)
    else:
        landmarks = profile.get("avatar_landmarks") or {}
        html = build_html(
            PHOTO,
            audio_mp3=(play or {}).get("audio"),
            text=(play or {}).get("text") if (play and voice_on) else None,
            lang=lang,
            landmarks=landmarks,
        )
        components.html(html, height=540)
    st.caption("🤖 This is an AI twin built by me. Answers come only from my profile.")

# ------------------------------------------------------------------ history
with chat_col:
    for m in ss.messages:
        with st.chat_message(m["role"], avatar="🧑‍💻" if m["role"] == "assistant" else None):
            st.write(m["content"])
