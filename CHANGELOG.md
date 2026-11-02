# Changelog

## 1.0.0
- Complete rewrite: src-layout package, SQLite + FTS5, staged resumable indexing, plan-based agent, safe export, Streamlit UI.

## 1.1.0
- Tidy up: exact-duplicate finder with visual review, opt-in reversible moves, undo history, move-from-chat.

## 1.2.0
- Similar-shot groups with best-photo suggestion, defect photo suggestions and labels, smart LLM filters (time of day, weekday, orientation, people count, near a place, quality).

## 1.3.0
- Accuracy tooling: `aperture eval-plans`, `aperture eval` (golden set, strictness sweep), fuzz and scale tests.

## 1.4.0
- Agent loop: the model picks tools step by step, checks results with a vision model, and builds replies from tool facts. Turn off with `agentic=false`.
- UI redesign: grouped navigation, logo, hero and stat cards, setup checklist, suggestion chips, photo tiles with density setting, "How I found this" timeline, light and dark themes.
