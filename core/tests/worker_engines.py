"""Stand-in engines the test worker process can be told to use (`--allow-custom-engine`). They run INSIDE the sandboxed worker, so what they do is what a real engine could do."""

from __future__ import annotations

import json
import os
import socket
import time


class EchoEngine:
    """Loads nothing; answers a fixed JSON reply in pieces, and records what folder it was given."""

    def __init__(self) -> None:
        self.path = ""

    def load(self, path: str) -> None:
        self.path = path
        if not os.path.isdir(path):
            raise FileNotFoundError(path)

    def unload(self) -> None:
        self.path = ""

    def stream(self, prompt, max_tokens):
        reply = json.dumps({"answer": "Due 1250.50", "citations": [{"passage": 1, "quote": "1250.50"}]})
        for at in range(0, len(reply), 7):
            yield reply[at : at + 7]


class ProbeEngine(EchoEngine):
    """The prompt is `host:port`. Reports what the process can do with the network, with Unix sockets and with its environment."""

    def stream(self, prompt, max_tokens):
        host, _, port = prompt.partition(":")
        result: dict[str, object] = {}
        for label, kind in (("tcp", socket.SOCK_STREAM), ("udp", socket.SOCK_DGRAM)):
            try:
                s = socket.socket(socket.AF_INET, kind)
                if label == "tcp":
                    s.connect((host, int(port)))
                    result[label] = "CONNECTED"
                else:  # creating a datagram socket is not the leak; sending data out is
                    s.sendto(b"exfiltrated", (host, int(port)))
                    result[label] = "SENT"
                s.close()
            except OSError as e:
                result[label] = f"blocked:{e.errno}"
        try:
            a, b = socket.socketpair()
            a.close()
            b.close()
            result["unix"] = "ok"
        except OSError as e:
            result["unix"] = f"blocked:{e.errno}"
        for label, where in (
            ("write_tmp", "/tmp"),
            ("write_home", os.path.expanduser("~")),
        ):  # file writes: denied by the macOS profile; Linux confines the network only
            try:
                with open(os.path.join(where, f"atlas-probe-{os.getpid()}"), "w") as handle:
                    handle.write("x")
                os.unlink(handle.name)
                result[label] = "WROTE"
            except OSError as e:
                result[label] = f"blocked:{e.errno}"
        result["secret_in_env"] = "ATLAS_TEST_SECRET" in os.environ
        result["env_keys"] = sorted(os.environ)
        yield json.dumps(result)


class SlowEngine(EchoEngine):
    """Streams many pieces slowly, so a consumer can stop early."""

    def stream(self, prompt, max_tokens):
        for n in range(200):
            time.sleep(0.02)
            yield f"p{n} "


class SilentEngine(EchoEngine):
    def stream(self, prompt, max_tokens):
        time.sleep(30)
        yield "never"


class CrashEngine(EchoEngine):
    def stream(self, prompt, max_tokens):
        os._exit(7)
        yield ""
