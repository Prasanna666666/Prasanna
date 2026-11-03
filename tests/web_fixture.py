"""A fake-but-real Lumo backend for tests and design previews: real database, real thumbnail files, scripted agent."""

from __future__ import annotations

import colorsys
import threading
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from aperture.agent.service import AgentReply
from aperture.bootstrap import AppContext
from aperture.config import Paths, preview_rel, thumb_rel
from aperture.web.server import Web, make_handler

PLACES = ["Goa, India", "Bengaluru, India", "Eindhoven, Netherlands", "Lisbon, Portugal", None]


def make_photos(ctx: AppContext, n: int = 70) -> list[int]:
    conn = ctx.db.connect()
    ids = []
    try:
        for i in range(1, n + 1):
            hue = (i * 0.07) % 1.0
            r, g, b = (int(255 * c) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.92))
            for rel, size in ((thumb_rel(i), (360, 360)), (preview_rel(i), (1200, 800))):
                path = ctx.paths.data / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                img = Image.new("RGB", size, (r, g, b))
                d = ImageDraw.Draw(img)
                d.ellipse([size[0] * .15, size[1] * .15, size[0] * .85, size[1] * .85], outline=(255, 255, 255), width=max(4, size[0] // 40))
                img.save(path, "JPEG", quality=82)
            conn.execute(
                "INSERT INTO items(id, path, rel_path, kind, taken_at, place, camera, thumb, preview, meta_done, clip_done) VALUES (?,?,?,?,?,?,?,?,?,1,1)",
                (i, f"/photos/IMG_{i:04d}.jpg", f"Trips/IMG_{i:04d}.jpg", "image", f"2025-0{1 + i % 9}-1{i % 9} 1{i % 10}:20:00",
                 PLACES[i % len(PLACES)], "iPhone 15 Pro", thumb_rel(i), preview_rel(i)))
            ids.append(i)
        conn.commit()
    finally:
        conn.close()
    return ids


class ScriptedAgent:
    """Answers like the real agent would, without a model."""

    def __init__(self, ids):
        self.ids, self.asked = ids, []

    def ask(self, request, previous_ids=None, history=None):
        self.asked.append((request, previous_ids, history))
        low = request.lower()
        if "boom" in low:
            raise RuntimeError("Ollama is not reachable")
        if any(w in low for w in ("photo", "beach", "dog", "pics", "sunset")):
            ids = np.array(self.ids if "all" in low else self.ids[:41])
            return AgentReply("results", f"I found **{len(ids)} photos** matching your request.", ids=ids, notes=["3 photos have no GPS, so the place could not be checked."])

        def words():
            for w in ("Sure, ", "happy ", "to ", "help. ", "RAW keeps ", "all the sensor data."):
                time.sleep(0.03)
                yield w

        return AgentReply("chat", "", stream=words())


def make_ctx(tmp_path, n: int = 70):
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    ids = make_photos(ctx, n)
    agent = ScriptedAgent(ids)
    ctx.agent = lambda: agent
    ctx.search_ready = lambda: True
    ctx.llm = lambda: SimpleNamespace(health=lambda: (True, "ok"), unload=lambda: None)
    ctx.embedding_index = lambda: None
    ctx.search_embedder = lambda: None
    return ctx, agent, ids


def start_server(ctx, port: int = 0):
    from http.server import ThreadingHTTPServer

    web = Web(ctx, port)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(web))
    web.port = server.server_port
    server.RequestHandlerClass = make_handler(web)  # rebuilt now that the real port is known
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return web, server
