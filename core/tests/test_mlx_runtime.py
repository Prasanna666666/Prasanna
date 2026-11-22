"""WP3.4b: the MLX adapter against a FAKE `mlx_lm` (no model, no Apple Silicon): what it loads, how it loads it, and how it treats what comes back."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from conftest import CORPUS, T0, grant, labels, passage
from test_intelligence import FakeRuntime, context, world  # noqa: F401
from test_models import entry_dict, sha, signed  # noqa: F401

from atlas_core.gate import ContextBuilder
from atlas_core.intelligence import RuntimeFailure
from atlas_core.mlx_runtime import MlxEngine, MlxRuntime, build_prompt, parse_answer
from atlas_core.models import ModelStore
from atlas_core.policy import InMemoryGrants, PolicyEngine


class FakeMlx:
    def __init__(self, reply: str = "{}", fail: str | None = None) -> None:
        self.reply, self.fail, self.loads, self.runs = reply, fail, [], []

    def load(self, path, tokenizer_config=None):
        if self.fail == "load":
            raise OSError("/secret/path/leaked")
        self.loads.append((path, tokenizer_config))
        return "M", "T"

    def stream_generate(self, model, tokenizer, prompt, max_tokens):
        if self.fail == "run":
            raise RuntimeError("secret content in message")
        self.runs.append((model, tokenizer, prompt, max_tokens))
        for piece in (self.reply[: len(self.reply) // 2], self.reply[len(self.reply) // 2 :]):  # a real engine yields pieces
            yield SimpleNamespace(text=piece)


def verified(tmp_path, runtime="mlx"):
    d = tmp_path / "m1"
    d.mkdir(exist_ok=True)
    if d.joinpath("w.safetensors").exists():
        d.joinpath("w.safetensors").chmod(0o644)
    (d / "w.safetensors").write_bytes(b"w")
    manifest = signed([entry_dict("m1", {"w.safetensors": b"w"}, runtime=runtime)])
    store = ModelStore(tmp_path, manifest, b"k" * 32)
    store.import_model("m1")
    return store.stage(store.verify_for_load("m1"))


def ctx():
    _, token = PolicyEngine(InMemoryGrants([grant("documents")])).decide(["documents"], T0)
    return ContextBuilder(labels()).build(token, "What is due?", [passage(CORPUS[0], 0, 20), passage(CORPUS[0], 20, 40)], T0)


def runtime(fake: FakeMlx) -> MlxRuntime:
    return MlxRuntime(MlxEngine(lambda name: SimpleNamespace(load=fake.load, stream_generate=fake.stream_generate) if name == "mlx_lm" else pytest.fail(name)))


def test_load_passes_only_the_verified_folder_with_remote_code_off_and_offline_env(tmp_path):
    fake = FakeMlx()
    rt = runtime(fake)
    v = verified(tmp_path)
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(name, None)
    rt.load(v)
    assert fake.loads == [(str(v.root), {"trust_remote_code": False})] and rt.loaded() == {"m1"}
    assert os.environ["HF_HUB_OFFLINE"] == "1" and os.environ["TRANSFORMERS_OFFLINE"] == "1"
    rt.unload("m1")
    assert rt.loaded() == frozenset()


def test_a_stub_runtime_manifest_entry_is_not_loaded_by_mlx(tmp_path):
    with pytest.raises(RuntimeFailure):
        runtime(FakeMlx()).load(verified(tmp_path, runtime="stub"))


def test_missing_mlx_and_library_errors_become_content_free_failures(tmp_path):
    def missing(name):
        raise ModuleNotFoundError(name)

    with pytest.raises(RuntimeFailure) as e:
        MlxRuntime(MlxEngine(missing)).load(verified(tmp_path))
    assert str(e.value) == "load_failed"
    rt = runtime(FakeMlx(fail="load"))
    with pytest.raises(RuntimeFailure) as e:
        rt.load(verified(tmp_path))
    assert "secret" not in str(e.value)
    ok = runtime(FakeMlx(fail="run"))
    ok.load(verified(tmp_path))
    with pytest.raises(RuntimeFailure) as e:
        ok.complete("m1", ctx(), 32768)
    assert str(e.value) == "inference_failed"


def test_complete_before_load_fails():
    with pytest.raises(RuntimeFailure, match="not_loaded"):
        runtime(FakeMlx()).complete("m1", ctx(), 32768)


def test_the_prompt_marks_passages_as_untrusted_data_and_numbers_them():
    p = build_prompt(ctx())
    assert "untrusted data" in p and "[1] " in p and "[2] " in p and p.rstrip().endswith("JSON:") and "What is due?" in p


def test_a_prompt_over_the_context_budget_is_refused_not_cut(tmp_path):
    rt = runtime(FakeMlx())
    rt.load(verified(tmp_path))
    with pytest.raises(RuntimeFailure, match="context_too_large"):
        rt.complete("m1", ctx(), 10)


def test_citations_map_to_the_given_passages_only_and_bad_ones_are_dropped():
    c = ctx()
    raw = json.dumps({"answer": "A", "citations": [{"passage": 1, "quote": "x"}, {"passage": 9}, {"passage": True}, {"passage": "1"}, "junk", {"passage": 2}]})
    a = parse_answer("noise " + raw + " trailing", c)
    assert a.text == "A" and [x["evidence"] for x in a.citations] == [c.passages[0]["evidence"], c.passages[1]["evidence"]] and a.citations[0]["quote"] == "x"
    assert "quote" not in a.citations[1]


@pytest.mark.parametrize("raw", ["plain words", "{broken", '{"answer": 5}', "[]", ""])
def test_an_unparseable_reply_is_plain_uncited_text(raw):
    a = parse_answer(raw, ctx())
    assert a.citations == () and a.text == raw.strip()


def test_through_the_gateway_the_model_identity_is_mlx(tmp_path):
    fake = FakeMlx(json.dumps({"answer": "Due 1250.50", "citations": [{"passage": 1}]}))
    rt = runtime(fake)
    d = tmp_path / "primary-1"
    d.mkdir()
    (d / "w.safetensors").write_bytes(b"prim")
    manifest = signed([entry_dict("primary-1", {"w.safetensors": b"prim"}, runtime="mlx")])
    store = ModelStore(tmp_path, manifest, b"k" * 32)
    store.import_model("primary-1")
    from atlas_core.intelligence import Gateway, Router, Signals

    gw = Gateway(store, Router(manifest.entries()), rt, signals=Signals)
    a = gw.generate(ctx())
    assert (
        a.identity == ("primary-1", "primary", "mlx") and a.text == "Due 1250.50" and len(fake.runs) == 1 and fake.loads[0][1] == {"trust_remote_code": False}
    )
