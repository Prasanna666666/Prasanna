# Model runtime: verified loading, yielding, isolation (WP3.4)

All of this is verified on Linux with fake engines and stubs. **Nothing here has run a real model, and nothing about MLX, speed, memory, quality or macOS enforcement is claimed.**

## Verified-only loading (`models.py`)
- A signed manifest lists every approved model (hash of every file, lineage, licence, runtime, capabilities). A model not in it never loads; only safetensors/GGUF weights plus configuration and tokenizer data are accepted; no pickle, no code.
- Every path is opened **one component at a time with `O_NOFOLLOW`** from an open directory descriptor (a symlinked parent cannot redirect a manifest path out of the model folder, nor can the model folder itself be a link) and every digest is computed **from the open descriptor**.
- `stage()` builds the folder the runtime loads from: **only the manifest's files**, as hard links to the verified inodes (so a later rename or replacement of the original name cannot change what loads), each confirmed to be the inode that was hashed; where links are impossible a copy is hashed as it is written. Unmanifested files next to the weights are never visible to the loader. `still_verified()` detects an in-place change after loading; a staging folder is removed on unload and any left by a crash at start.
- Threat model: other processes and accidents. A process of the same user that deliberately rewrites a read-only file and its timestamps is not defended against.
- Tests: `tests/test_models.py` (parent symlink, deeper component, folder as link, extra files, rename after verify, in-place change, swap between verify and link, copy fallback, crash leftovers).

## Yielding and bounded waits (`intelligence.py`)
- Runtimes poll `should_stop` between pieces of output. Interactive requests never yield. A **background** inference stops (the caller gets `ModelUnavailable("preempted")` and may retry) when an interactive request is waiting for a different model or when memory pressure holds background work (`stop_background`, `pause_background`).
- An interactive request that needs another model waits at most `SWITCH_WAIT_SECONDS`, then `busy`; the scheduler admits one interactive plus one background inference.
- The memory need is the weights plus `context_tokens x kv_bytes_per_token` (`kv_bytes_per_token` is injected; **unmeasured here**, to be set from the Mac benchmark), so the `shrink_context` step really lowers it, and the smaller context is what runs.
- Tests: `tests/test_intelligence.py` (interactive arrives during a running background inference and progresses in well under the background job's natural duration; memory hold stops a running job; same-model interactive does not stop it; bounded wait; shrink lowers the need and the smaller context is used).

## Local-only boundary (`sandbox.py`, `worker.py`, `isolated.py`)
- The engine runs in a **separate worker process** that installs an OS network denial **before importing or loading anything** and reports it in its first message; a worker that cannot is never used (fail closed). Linux: a seccomp filter (no_new_privs) makes `socket()` fail for every domain except AF_UNIX and blocks `io_uring_setup`; it cannot be removed and is inherited. macOS: the worker is launched under `sandbox-exec` with a profile that denies network; **written from documentation and never run (UNVERIFIED)**.
- The worker gets a clean environment (no secrets), stderr is discarded, only a prompt string goes in and only text comes out (no grants, sources or context objects). A dead, silent or slow worker is a failure, never a hang; a consumer that stops early cancels the worker's generation.
- `MlxEngine` run in-process (development) sets best-effort offline variables only; that is **not** a network guarantee and is documented as such.
- Tests: `tests/test_isolated.py` (inside the worker TCP and UDP sockets are refused while Unix sockets work; the same probe succeeds without the sandbox; clean environment; fail-closed paths; cancel, crash, silence; the whole path through the gateway with the staged folder). Mutation check: removing the seccomp call makes the probe test fail.
- Not done: a test that the *real* MLX library opens no socket while loading (needs the Mac), the macOS profile run, and a network-isolation test on macOS.
