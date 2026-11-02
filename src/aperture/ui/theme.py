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
.block-container { padding-top: 2.2rem; max-width: 1280px; }
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


def hero(title: str, subtitle: str) -> None:
    st.html(f'<div class="ap-hero"><h1>{title}</h1><p>{subtitle}</p></div>')
