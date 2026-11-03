"""One shared model on an 8 GB Mac: no reloads, light defaults, short keep-alive."""

import json
import re
from pathlib import Path

from aperture.agent import llm
from aperture.config import Paths, Settings

LLM_SRC = Path(llm.__file__).read_text()


def test_every_request_uses_the_same_context_size():
    assert llm.NUM_CTX == 4096
    assert not re.findall(r'"num_ctx":\s*\d+', LLM_SRC), "a literal num_ctx makes Ollama reload the model"
    assert len(re.findall(r'"num_ctx": NUM_CTX', LLM_SRC)) >= 4  # text, plan, describe, judge


def test_text_and_vision_requests_send_identical_num_ctx(monkeypatch):
    sent = []
    monkeypatch.setattr(llm.OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": "{}"}})
    c = llm.OllamaVision("http://127.0.0.1:11434", "ministral-3:3b")
    c.complete_json("s", "u", {"type": "object"})
    c.complete_text("s", "u")
    c.describe(b"\xff\xd8x")
    c.judge(b"\xff\xd8x", "is it a dog?")
    ctxs = {p["options"]["num_ctx"] for p in sent}
    assert len(sent) == 4 and ctxs == {llm.NUM_CTX}
    assert {p["keep_alive"] for p in sent} == {"30m"}


def test_light_indexing_defaults_and_old_settings_migrate(tmp_path):
    d = Settings.defaults(Paths(tmp_path))
    assert (d.workers, d.batch_size) == (2, 8)
    paths = Paths(tmp_path)
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(json.dumps({"schema": 4, "workers": 3, "batch_size": 16, "page_size": 48}))
    s = Settings.load(paths)
    assert (s.workers, s.batch_size, s.page_size, s.schema) == (2, 8, 48, 9)
    paths.settings_file.write_text(json.dumps({"schema": 5, "workers": 4}))
    assert Settings.load(paths).workers == 4  # a deliberate choice made after v5 is kept
