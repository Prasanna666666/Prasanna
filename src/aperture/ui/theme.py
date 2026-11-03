"""Design tokens and global CSS.

Colours derive from ``currentColor`` and Streamlit's own theme, so the same
rules work in light mode, dark mode and the high-contrast option.  Interactive
elements keep the browser's focus ring (made more visible here) and animation
respects ``prefers-reduced-motion``.
"""

from __future__ import annotations

import streamlit as st

ACCENT = "#4f46e5"

_CSS = """
<style>
:root { --ap-accent: #4f46e5; --ap-radius: 14px; --ap-line: color-mix(in srgb, currentColor 14%, transparent);
        --ap-soft: color-mix(in srgb, currentColor 6%, transparent); --ap-muted: color-mix(in srgb, currentColor 62%, transparent); }
.block-container { max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.02em; }
h1 { font-weight: 700; }

/* focus is always visible for keyboard users */
button:focus-visible, [role="tab"]:focus-visible, input:focus-visible, [data-baseweb] :focus-visible {
  outline: 3px solid var(--ap-accent) !important; outline-offset: 2px !important; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }

/* sidebar brand + status */
.ap-brand { display:flex; align-items:center; gap:.65rem; padding:.2rem 0 .6rem; }
.ap-logo { width:34px; height:34px; border-radius:10px; display:grid; place-items:center; color:#fff; font-weight:700;
           background: conic-gradient(from 210deg, #4f46e5, #06b6d4, #22c55e, #f59e0b, #4f46e5); }
.ap-brand b { font-size:1.15rem; letter-spacing:-0.02em; }
.ap-brand small { display:block; color:var(--ap-muted); margin-top:-2px; }
.ap-chip { display:inline-flex; align-items:center; gap:.4rem; padding:.18rem .6rem; border:1px solid var(--ap-line);
           border-radius:999px; font-size:.78rem; margin:.15rem .25rem .15rem 0; background:var(--ap-soft); }
.ap-dot { width:.55rem; height:.55rem; border-radius:50%; background:#9ca3af; display:inline-block; }
.ap-dot.ok { background:#16a34a; } .ap-dot.warn { background:#d97706; } .ap-dot.bad { background:#dc2626; }

/* hero */
.ap-hero { padding:2.2rem 1.6rem 1.6rem; border:1px solid var(--ap-line); border-radius:22px; margin-bottom:1rem;
  background: radial-gradient(1200px 300px at 0% 0%, color-mix(in srgb, var(--ap-accent) 16%, transparent), transparent 60%),
              radial-gradient(900px 260px at 100% 100%, color-mix(in srgb, #06b6d4 14%, transparent), transparent 60%); }
.ap-hero h1 { margin:0 0 .35rem; font-size:2.1rem; }
.ap-hero p { margin:0; color:var(--ap-muted); font-size:1.02rem; }

/* stat cards */
.ap-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.75rem; margin:.4rem 0 1rem; }
.ap-stat { border:1px solid var(--ap-line); border-radius:var(--ap-radius); padding:.8rem 1rem; background:var(--ap-soft); }
.ap-stat b { display:block; font-size:1.55rem; letter-spacing:-0.02em; }
.ap-stat span { color:var(--ap-muted); font-size:.82rem; }

/* photo tiles: uniform squares, soft corners, gentle hover */
[class*="st-key-tile"] { border-radius:var(--ap-radius); }
[class*="st-key-tile"] [data-testid="stImage"] img { aspect-ratio:1/1; object-fit:cover; width:100%; border-radius:var(--ap-radius);
  transition: transform .15s ease, box-shadow .15s ease; }
[class*="st-key-tile"]:hover [data-testid="stImage"] img { transform: translateY(-2px); box-shadow:0 8px 22px rgba(0,0,0,.18); }
[class*="st-key-tile"] [data-testid="stImageCaption"] { font-size:.74rem; color:var(--ap-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
[class*="st-key-tile"] button { width:100%; }

/* agent trace timeline */
.ap-trace { border-left:2px solid var(--ap-line); margin:.2rem 0 .2rem .5rem; padding-left:1rem; }
.ap-step { position:relative; margin:0 0 .85rem; }
.ap-step::before { content:""; position:absolute; left:-1.34rem; top:.35rem; width:.6rem; height:.6rem; border-radius:50%; background:var(--ap-accent); }
.ap-step b { font-size:.9rem; } .ap-step i { color:var(--ap-muted); display:block; font-size:.84rem; }
.ap-step code { display:block; white-space:pre-wrap; font-size:.76rem; margin-top:.25rem; background:var(--ap-soft); padding:.35rem .5rem; border-radius:8px; }

/* checklist (onboarding) */
.ap-check { display:flex; gap:.7rem; align-items:flex-start; padding:.55rem 0; border-bottom:1px solid var(--ap-line); }
.ap-check:last-child { border-bottom:none; }
.ap-tick { flex:none; width:1.35rem; height:1.35rem; border-radius:50%; display:grid; place-items:center; font-size:.8rem; color:#fff; background:#9ca3af; }
.ap-tick.done { background:#16a34a; }
.ap-check small { color:var(--ap-muted); display:block; }

/* tabs & buttons */
[data-baseweb="tab-list"] { gap:.25rem; }
button[kind="primary"] { border-radius:10px; font-weight:600; }
[data-testid="stChatMessage"] { border-radius:var(--ap-radius); }

/* ---------- chat: a messenger, not a form ----------
   Messages carry a hidden marker (.ap-user-marker / .ap-bot-marker, added in chat.py) so the styling does not depend on
   Streamlit's internal avatar names, which differ between versions. */
.stApp { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Segoe UI", system-ui, sans-serif; }
.block-container { padding-top: 4.5rem; }
.ap-chat-head { display:flex; align-items:baseline; gap:.7rem; padding:.1rem 0 .2rem; }
.ap-chat-head b { font-size:1.35rem; letter-spacing:-0.02em; }
.ap-chat-head span { color:var(--ap-muted); font-size:.85rem; }
.ap-user-marker, .ap-bot-marker { display:none; }
[data-testid="stElementContainer"]:has(> .ap-user-marker), [data-testid="stElementContainer"]:has(.ap-user-marker),
[data-testid="stElementContainer"]:has(.ap-bot-marker) { display:none; }

[data-testid="stChatMessage"] { background:transparent; border:none; padding:.4rem 0; gap:.8rem; max-width:980px; margin:0 auto .3rem; }
[data-testid="stChatMessageContent"] { font-size:1.02rem; line-height:1.6; }
[data-testid="stChatMessage"] p { margin:0 0 .5rem; }

/* you: right-aligned accent bubble, no avatar */
[data-testid="stChatMessage"]:has(.ap-user-marker) { flex-direction:row-reverse; }
[data-testid="stChatMessage"]:has(.ap-user-marker) > [data-testid^="stChatMessageAvatar"] { display:none; }
[data-testid="stChatMessage"]:has(.ap-user-marker) [data-testid="stChatMessageContent"] {
  flex:0 1 auto; margin:0 0 0 auto !important; width:fit-content; max-width:74%; color:#fff; padding:.7rem 1.05rem; border-radius:20px 20px 6px 20px;
  background:linear-gradient(135deg, var(--ap-accent), #7c6ff7); box-shadow:0 6px 18px color-mix(in srgb, var(--ap-accent) 28%, transparent); }
[data-testid="stChatMessage"]:has(.ap-user-marker) [data-testid="stChatMessageContent"] * { color:#fff; }

/* Lumo: gradient sparkle badge, roomy text, quiet extras */
[data-testid="stChatMessage"]:has(.ap-bot-marker) > [data-testid^="stChatMessageAvatar"] {
  background:linear-gradient(135deg, var(--ap-accent), #06b6d4); color:#fff; border-radius:12px; width:2.2rem; height:2.2rem;
  box-shadow:0 4px 12px color-mix(in srgb, var(--ap-accent) 30%, transparent); }
[data-testid="stChatMessage"]:has(.ap-bot-marker) > [data-testid^="stChatMessageAvatar"] * { color:#fff; }
[data-testid="stChatMessage"] [data-testid="stAlert"] { background:transparent; border:none; padding:0; }
[data-testid="stChatMessage"] [data-testid="stAlertContainer"] { border:none; border-radius:12px; font-size:.9rem; padding:.55rem .8rem;
  background:color-mix(in srgb, var(--ap-accent) 9%, transparent); }
[data-testid="stChatMessage"] [data-testid="stAlertContainer"] * { color:inherit; }
[data-testid="stChatMessage"] details { border:none !important; background:transparent !important; }
[data-testid="stChatMessage"] details summary { color:var(--ap-muted); font-size:.86rem; padding-left:0; }
[data-testid="stChatMessage"] details summary:hover { color:var(--ap-accent); }
[data-testid="stStatus"], [data-testid="stStatusWidget"] { border-radius:14px; border:1px solid var(--ap-line); }

/* input: a floating pill with a round send button */
[data-testid="stChatInput"] { max-width:820px; margin:0 auto; }
[data-testid="stChatInput"] > div { border-radius:999px; border:1px solid var(--ap-line); padding:.2rem .35rem .2rem 1rem;
  box-shadow:0 10px 30px color-mix(in srgb, var(--ap-accent) 12%, transparent), 0 1px 3px rgba(0,0,0,.06); transition:box-shadow .15s, border-color .15s; }
[data-testid="stChatInput"] > div:focus-within { border-color:var(--ap-accent);
  box-shadow:0 0 0 3px color-mix(in srgb, var(--ap-accent) 22%, transparent), 0 10px 30px color-mix(in srgb, var(--ap-accent) 14%, transparent); }
[data-testid="stChatInput"] textarea { font-size:1rem; }
[data-testid="stChatInput"] button { background:var(--ap-accent); color:#fff; border-radius:50%; width:2.2rem; height:2.2rem; }
[data-testid="stChatInput"] button:disabled { background:var(--ap-soft); color:var(--ap-muted); }
[data-testid="stChatInput"] button svg { fill:currentColor; }

/* suggestion cards on the first screen */
[class*="st-key-idea_"] button { text-align:left; justify-content:flex-start; min-height:5.2rem; padding:1rem 1.1rem; border-radius:16px;
  border:1px solid var(--ap-line); background:var(--ap-soft); font-weight:500; white-space:normal; line-height:1.4;
  transition:transform .15s ease, box-shadow .15s ease, border-color .15s ease; }
[class*="st-key-idea_"] button:hover { border-color:var(--ap-accent); transform:translateY(-2px); box-shadow:0 10px 24px color-mix(in srgb, var(--ap-accent) 16%, transparent); }
[class*="st-key-idea_"] button p { text-align:left; }
.ap-hero h1 { background:linear-gradient(90deg, var(--ap-accent), #06b6d4); -webkit-background-clip:text; background-clip:text; color:transparent; }
.ap-eyebrow { display:inline-block; font-size:.78rem; letter-spacing:.06em; text-transform:uppercase; color:var(--ap-accent); font-weight:600; margin-bottom:.5rem; }

/* high contrast option */
body.ap-hc, .ap-hc-on { --ap-line: currentColor; }
</style>
"""

_HIGH_CONTRAST = """
<style>
:root { --ap-line: currentColor !important; --ap-muted: currentColor !important; }
.ap-stat, .ap-chip, .ap-hero { border-width:2px !important; }
[class*="st-key-tile"] [data-testid="stImageCaption"] { color: currentColor !important; font-size:.82rem !important; }
</style>
"""


def inject(high_contrast: bool = False) -> None:
    """Add the global stylesheet (call once per run, before other output)."""
    st.html(_CSS + (_HIGH_CONTRAST if high_contrast else ""))


def chip(label: str, state: str = "idle") -> str:
    """HTML for a small status pill; ``state`` is ok | warn | bad | idle."""
    cls = state if state in ("ok", "warn", "bad") else ""
    return f'<span class="ap-chip"><span class="ap-dot {cls}" aria-hidden="true"></span>{label}</span>'


def stats(items: list[tuple[str, str]]) -> None:
    cards = "".join(f'<div class="ap-stat"><b>{value}</b><span>{label}</span></div>' for label, value in items)
    st.html(f'<div class="ap-stats" role="list">{cards}</div>')


def hero(title: str, subtitle: str, eyebrow: str = "") -> None:
    tag = f'<span class="ap-eyebrow">{eyebrow}</span><br>' if eyebrow else ""
    st.html(f'<div class="ap-hero">{tag}<h1>{title}</h1><p>{subtitle}</p></div>')
