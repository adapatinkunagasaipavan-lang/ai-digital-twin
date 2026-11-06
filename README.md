# 🧑‍💻 AI Digital Twin

A talking AI version of me. Interviewers can **type or speak** a question, and my twin answers
**out loud in my voice-style, with my photo lip-syncing**, using only facts from my profile.

Built with Python + Streamlit. Works with or without paid keys.

| Feature | How |
|---|---|
| Brain | Claude API, grounded on `profile.yaml` (never invents facts). Falls back to an offline matcher if no key / API down |
| Voice out | `edge-tts` neural voices (English-India, Telugu), free, no key |
| Voice in | `st.audio_input` + Google web speech, free, no key |
| Avatar (free) | Canvas animation of my photo: lip-sync driven by real audio loudness, blinking, head sway |
| Avatar (realistic) | Optional D-ID API: photo + text -> talking video |
| Languages | English and Telugu |

## 🚀 Run locally

```bash
git clone https://github.com/<you>/ai-digital-twin.git
cd ai-digital-twin
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. It works immediately in offline mode.
For full answers add a Claude key (below).

## ✏️ Make it yours (2 minutes)

1. Edit **`profile.yaml`**: name, summary, skills, projects, FAQ answers. Replace every `[placeholder]`.
2. Replace **`assets/photo.jpg`** with your photo (front-facing, mouth closed, plain background, ~720x900).
3. If the eyes or mouth look misplaced, tick **Calibrate face points** in the sidebar and adjust
   `avatar_landmarks` in `profile.yaml` (fractions of photo width/height; defaults are in `twin/avatar.py`).

## 🔑 API keys (optional)

| Key | What for | Where |
|---|---|---|
| `ANTHROPIC_API_KEY` | Full, natural answers from Claude | https://console.anthropic.com |
| `DID_API_KEY` | Realistic video mode | https://studio.d-id.com |

Local: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in (git-ignored),
or export the variables. You can also paste keys into the sidebar for a single session.
**Never commit keys.**

## ☁️ Deploy on Streamlit Community Cloud (free)

1. Push this folder to a GitHub repo.
2. Go to https://share.streamlit.io -> **Create app** -> pick the repo, branch `main`, file `app.py`.
3. **Advanced settings -> Secrets**: paste
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
4. Deploy, then share the URL with interviewers.

Docker alternative: `docker build -t twin . && docker run -p 8501:8501 -e ANTHROPIC_API_KEY=... twin`

## 🧱 How it works

```
 question (type / mic) ──► brain.py ──► Claude (profile as context) ──► answer text
                                  └──► offline matcher (fallback)            │
                                                                             ▼
                 avatar.html (canvas) ◄── audio (edge-tts mp3) ◄──── voice.py
                 lip-sync = loudness of the audio via Web Audio AnalyserNode
```

- `app.py` : Streamlit UI and flow
- `twin/brain.py` : prompt building, Claude call, offline fallback
- `twin/voice.py` : text-to-speech and speech-to-text
- `twin/avatar.py` + `avatar.html` : the animated photo component
- `twin/did_client.py` : optional D-ID video mode

## ✅ Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## ⚠️ Notes

- The twin states that it is an AI and only answers from `profile.yaml`.
- Browsers may block autoplay audio until you click once; a **Play answer** button appears if so.
- Voice input uses a free Google endpoint and may be rate-limited; typing always works.
- The D-ID mode is implemented against the public API docs but needs your key to try.
- If your repo is public, your photo and profile are public too.
