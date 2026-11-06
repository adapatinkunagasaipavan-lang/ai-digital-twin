import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twin import did_client
from twin.avatar import build_html
from twin.brain import Brain, build_system_prompt, has_placeholders, load_profile, offline_answer
from twin.voice import speakable

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {
    "name": "Test Person",
    "summary": "I build AI apps in Python.",
    "skills": {"languages": ["Python", "SQL"]},
    "projects": [{"name": "Twin", "description": "A talking avatar.", "tech": ["Streamlit"]}],
    "education": [{"degree": "B.Tech", "school": "ABC", "period": "2020-2024"}],
    "faq": [{"q": "Why should we hire you?", "a": "Because I ship."}],
}


def test_profile_file_loads():
    p = load_profile(ROOT / "profile.yaml")
    assert p["name"]
    assert has_placeholders(p)  # template ships with placeholders


def test_system_prompt_contains_profile_and_rules():
    s = build_system_prompt(PROFILE, "en")
    assert "Test Person" in s and "Python" in s and "first person" in s
    assert "Telugu script" in build_system_prompt(PROFILE, "te")


def test_offline_answers_route_by_topic():
    assert "Python" in offline_answer(PROFILE, "What skills do you have?")
    assert "talking avatar" in offline_answer(PROFILE, "Tell me about your projects")
    assert "B.Tech" in offline_answer(PROFILE, "Where did you study?")
    assert offline_answer(PROFILE, "Why should we hire you?") == "Because I ship."
    assert "do not have that" in offline_answer(PROFILE, "zzz qqq xyz")
    assert "Hello" in offline_answer(PROFILE, "hi")
    assert "build AI apps" in offline_answer(PROFILE, "Tell me about yourself")


def test_brain_without_key_is_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text, src = Brain(PROFILE).reply([], "skills?")
    assert src == "offline" and "Python" in text


def test_brain_falls_back_when_api_fails(monkeypatch):
    b = Brain(PROFILE, api_key="bad")

    class Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("network down")

    b._client = Boom()
    text, src = b.reply([], "what skills do you have")
    assert src.startswith("offline") and "Python" in text


def test_speakable_strips_markdown_and_urls():
    assert speakable("**Hi** see https://x.com now") == "Hi see now"


def test_avatar_html_embeds_config():
    html = build_html(ROOT / "assets" / "photo.jpg", audio_mp3=b"ID3abc", lang="te", debug=True)
    assert "__CONFIG__" not in html
    assert '"lang": "te-IN"' in html and '"debug": true' in html and "<canvas" in html
    assert '"mesh": {' in html and "init3D" in html        # 3D face mesh is embedded


def test_did_flow(monkeypatch):
    calls = []

    class R:
        def __init__(self, data, code=200):
            self._d, self.status_code, self.text = data, code, ""

        def json(self):
            return self._d

    def fake_post(url, **kw):
        calls.append(url)
        return R({"id": "t1"} if url.endswith("/talks") else {"url": "https://img"})

    states = iter([{"status": "started"}, {"status": "done", "result_url": "https://vid.mp4"}])
    monkeypatch.setattr(did_client.requests, "post", fake_post)
    monkeypatch.setattr(did_client.requests, "get", lambda url, **kw: R(next(states)))
    monkeypatch.setattr(did_client.time, "sleep", lambda s: None)

    img = did_client.upload_image("key", ROOT / "assets" / "photo.jpg")
    assert img == "https://img"
    assert did_client.create_talk("key", img, "hello") == "https://vid.mp4"


def test_streamlit_app_flow(monkeypatch):
    """Boot the real app headlessly, ask a question, expect an answer in the chat."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    at.chat_input[0].set_value("What skills do you have?").run()
    assert not at.exception
    roles = [m.avatar for m in at.chat_message]
    assert len(at.chat_message) == 2 and roles[1] == "🧑‍💻"
    assert "skills" in at.chat_message[1].markdown[0].value.lower()


def test_face_mesh_is_consistent():
    import json

    m = json.loads((ROOT / "assets" / "face_mesh.json").read_text())
    n = m["n"]
    assert len(m["pos"]) == 3 * n and len(m["nrm"]) == 3 * n
    for k in ("wHead", "wJaw", "wMouth", "wBlinkA", "wBlinkB"):
        assert len(m[k]) == n
    assert max(m["idx"]) < n and len(m["idx"]) % 3 == 0
    assert all(0 <= w <= 1 for w in m["wJaw"])


def test_avatar3d_html_embeds_config_and_imports():
    from twin.avatar3d import build_html as b3
    html = b3(audio_mp3=b"ID3abc", text="hello there", words=["hello", "there"],
              wtimes=[0, 400], wdurations=[350, 400], lang="te", glb_urls=["https://x/y.glb"])
    assert "talkinghead" in html and "three" in html
    assert "__CONFIG__" not in html and "__THREE__" not in html
    assert "SUQzYWJj" in html            # base64 of the audio
    assert "https://x/y.glb" in html and "te-IN" in html


def test_tts_timed_parses_word_boundaries(monkeypatch):
    import edge_tts
    from twin import voice

    class FakeComm:
        def __init__(self, *a, **k): pass
        async def stream(self):
            yield {"type": "audio", "data": b"abc"}
            yield {"type": "WordBoundary", "offset": 5_000_000, "duration": 3_000_000, "text": "Hello"}
            yield {"type": "WordBoundary", "offset": 9_000_000, "duration": 2_000_000, "text": "world"}
            yield {"type": "audio", "data": b"def"}

    monkeypatch.setattr(edge_tts, "Communicate", FakeComm)
    audio, words, wt, wd = voice.tts_timed("Hello world", "en")
    assert audio == b"abcdef" and words == ["Hello", "world"]
    assert wt == [500.0, 900.0] and wd == [300.0, 200.0]
