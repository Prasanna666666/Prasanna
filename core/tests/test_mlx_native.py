"""Real MLX inference inside the real isolated worker on macOS (sandbox-exec). Skipped unless a model folder is provided: the CI `macos-mlx` job downloads a small public one.

It proves the real library loads and generates under the sandbox profile (network denied, writes denied). It says nothing about speed, memory or answer quality of the models
the owner will choose; those are measurements for the real hardware and models.
"""

from __future__ import annotations

import os
import sys

import pytest

from atlas_core.isolated import IsolatedEngine

MODEL = os.environ.get("ATLAS_MLX_MODEL_DIR")
pytestmark = pytest.mark.skipif(sys.platform != "darwin" or not MODEL, reason="needs macOS, mlx-lm and a model folder (ATLAS_MLX_MODEL_DIR)")


def test_a_real_model_loads_and_generates_inside_the_sandboxed_worker():
    engine = IsolatedEngine("mlx")
    try:
        engine.load(MODEL or "")
        assert engine.network_denied == "launcher"  # the worker really ran under sandbox-exec
        text = "".join(engine.stream("The capital of France is", 12))
        assert text.strip(), "the real model produced no text"
    finally:
        engine.close()


def test_the_sandboxed_worker_with_the_real_library_still_cannot_reach_the_network_or_write():
    engine = IsolatedEngine("mlx")
    try:
        engine.load(MODEL or "")
        import json
        import socket
        import subprocess

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        probe = (
            "import socket,sys,json\n"
            "r={}\n"
            "try:\n s=socket.socket(); s.connect(('127.0.0.1',int(sys.argv[1]))); r['tcp']='CONNECTED'\n"
            "except OSError as e:\n r['tcp']='blocked'\n"
            "try:\n open('/tmp/atlas-mlx-probe','w').write('x'); r['write']='WROTE'\n"
            "except OSError:\n r['write']='blocked'\n"
            "print(json.dumps(r))\n"
        )
        from atlas_core import sandbox

        done = subprocess.run(
            [*sandbox.launch_prefix(), sys.executable, "-c", probe, str(listener.getsockname()[1])], capture_output=True, text=True, check=False, timeout=60
        )
        assert json.loads(done.stdout) == {"tcp": "blocked", "write": "blocked"}
        listener.close()
    finally:
        engine.close()
