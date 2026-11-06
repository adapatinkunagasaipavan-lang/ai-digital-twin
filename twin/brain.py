"""The twin's brain: answers questions from profile.yaml.

Uses the Claude API when a key is available. Without a key (or if the API
fails) it falls back to a small offline keyword matcher, so the demo never
breaks in front of an interviewer.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

import yaml

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

LANG_NAMES = {"en": "English", "te": "Telugu"}


# ---------------------------------------------------------------- profile
def load_profile(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def has_placeholders(profile: dict) -> bool:
    """True if any string in the profile still starts with '['."""
    def walk(x) -> Iterable[str]:
        if isinstance(x, str):
            yield x
        elif isinstance(x, dict):
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)

    return any(s.strip().startswith("[") for s in walk(profile))


def profile_to_text(profile: dict) -> str:
    """Flatten the profile into plain text for the LLM prompt."""
    lines: list[str] = []
    p = profile
    lines.append(f"Name: {p.get('name', '')}")
    if p.get("headline"):
        lines.append(f"Headline: {p['headline']}")
    if p.get("location"):
        lines.append(f"Location: {p['location']}")
    if p.get("summary"):
        lines.append(f"Summary: {_clean(p['summary'])}")
    if p.get("skills"):
        lines.append("Skills:")
        for cat, items in p["skills"].items():
            lines.append(f"  - {cat}: {', '.join(map(str, items))}")
    for e in p.get("experience", []) or []:
        lines.append(f"Experience: {e.get('role')} at {e.get('company')} ({e.get('period')})")
        for h in e.get("highlights", []) or []:
            lines.append(f"  - {h}")
    for pr in p.get("projects", []) or []:
        lines.append(f"Project: {pr.get('name')} - {_clean(pr.get('description', ''))} "
                     f"[tech: {', '.join(map(str, pr.get('tech', []) or []))}]")
    for ed in p.get("education", []) or []:
        lines.append(f"Education: {ed.get('degree')}, {ed.get('school')} ({ed.get('period')})")
    if p.get("strengths"):
        lines.append("Strengths: " + "; ".join(map(str, p["strengths"])))
    if p.get("goals"):
        lines.append(f"Goals: {_clean(p['goals'])}")
    for qa in p.get("faq", []) or []:
        lines.append(f"Q: {qa.get('q')}\nA: {_clean(qa.get('a', ''))}")
    return "\n".join(lines)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def build_system_prompt(profile: dict, lang: str = "en") -> str:
    name = profile.get("name", "the candidate")
    language = LANG_NAMES.get(lang, "English")
    script_note = " Write Telugu in Telugu script." if lang == "te" else ""
    return (
        f"You are the AI digital twin of {name}. You are talking to an interviewer, "
        f"and your answers are SPOKEN ALOUD by an avatar.\n\n"
        f"Rules:\n"
        f"- Speak in first person as {name}.\n"
        f"- Use ONLY facts from the PROFILE below. Never invent employers, numbers, "
        f"degrees or skills. If something is not in the profile, say you would "
        f"rather discuss that with the real {name} directly.\n"
        f"- If asked, be open that you are an AI twin built by {name}.\n"
        f"- Keep it to 2-4 short, natural sentences. No markdown, lists, emojis or URLs "
        f"(they sound bad when spoken).\n"
        f"- Reply in {language}.{script_note}\n\n"
        f"PROFILE:\n{profile_to_text(profile)}"
    )


# -------------------------------------------------------- offline fallback
_STOP = set(
    "a an the is are was were be to of in on at for and or with about you your "
    "me my i do does did what how why who tell can could would please this that it yourself".split()
)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z]+", text.lower()) if w not in _STOP and len(w) > 2}


def _chunks(profile: dict) -> list[tuple[str, str, str]]:
    """(keywords, spoken answer) pairs built from the profile."""
    name = profile.get("name", "me")
    out: list[tuple[str, str, str]] = []
    for qa in profile.get("faq", []) or []:
        out.append(("faq", qa.get("q", ""), _clean(qa.get("a", ""))))
    if profile.get("summary"):
        out.append(("intro about yourself introduce who background", "", _clean(profile["summary"])))
    skills = profile.get("skills") or {}
    if skills:
        flat = ", ".join(str(s) for items in skills.values() for s in items)
        out.append(("skills technologies tech stack tools languages know good at", "",
                    f"My main skills are {flat}."))
    for pr in profile.get("projects", []) or []:
        out.append((f"project projects built build work {pr.get('name', '')} "
                    f"{' '.join(map(str, pr.get('tech', []) or []))}", "",
                    f"{pr.get('name')}: {_clean(pr.get('description', ''))}"))
    for e in profile.get("experience", []) or []:
        hl = " ".join(map(str, (e.get("highlights", []) or [])[:2]))   # keep the spoken answer short
        out.append(("experience work job internship company career role", "",
                    f"I worked as {e.get('role')} at {e.get('company')} "
                    f"({e.get('period')}). {_clean(hl)}"))
    for ed in profile.get("education", []) or []:
        out.append(("education degree college university study studied school qualification", "",
                    f"I did my {ed.get('degree')} at {ed.get('school')} ({ed.get('period')})."))
    if profile.get("strengths"):
        out.append(("strength strengths best qualities good", "",
                    "My strengths are: " + "; ".join(map(str, profile["strengths"])) + "."))
    if profile.get("goals"):
        out.append(("goal goals future plan five years looking want career", "", _clean(profile["goals"])))
    c = profile.get("contact") or {}
    if c:
        out.append(("contact email reach github linkedin", "",
                    "You can reach me at " + ", ".join(f"{k}: {v}" for k, v in c.items()) + "."))
    return out


def offline_answer(profile: dict, message: str) -> str:
    name = profile.get("name", "")
    msg = message.lower().strip()
    if re.fullmatch(r"(hi|hello|hey|namaste|namaskaram)\W*", msg):
        return f"Hello! I am the AI digital twin of {name}. Ask me about my skills, projects or experience."
    if re.search(r"about (yourself|you)\b|introduce|who are you|walk me through", msg):
        if profile.get("summary"):
            return _clean(profile["summary"])
    q = _tokens(message)
    best, best_score = None, 0.0
    for keywords, question, answer in _chunks(profile):
        score = len(q & _tokens(keywords)) + 2 * len(q & _tokens(question))
        if keywords == "faq" and question and _tokens(question) and q:
            overlap = len(q & _tokens(question)) / len(_tokens(question))
            score += 3 * overlap
        if score > best_score:
            best, best_score = answer, score
    if best:
        return best
    return (f"I do not have that in my profile, so I would rather discuss it with the "
            f"real {name} directly. You can ask me about my skills, projects, education or goals.")


# ------------------------------------------------------------------ brain
class Brain:
    def __init__(self, profile: dict, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.profile = profile
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

    @property
    def uses_llm(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def reply(self, history: list[dict], message: str, lang: str = "en") -> tuple[str, str]:
        """Return (answer, source) where source is 'claude' or 'offline'."""
        if not self.uses_llm:
            return offline_answer(self.profile, message), "offline"
        try:
            msgs = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
            msgs.append({"role": "user", "content": message})
            resp = self._get_client().messages.create(
                model=self.model,
                max_tokens=350,
                system=build_system_prompt(self.profile, lang),
                messages=msgs,
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
            if text:
                return text, "claude"
        except Exception as exc:  # network, auth, quota...
            return offline_answer(self.profile, message), f"offline ({type(exc).__name__})"
        return offline_answer(self.profile, message), "offline"
