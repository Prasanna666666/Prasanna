# Verifying O-16 (sealed hand-over) on the owner's Mac

Run these on the Mac, in Terminal, in order. Use **invented test files only** (no real documents) for steps 4 to 8. Everything printed is what a reviewer needs: paste the full output of each numbered step back. Nothing here changes your real documents; the sealed hand-over is off unless you do step 3.

Needs: Docker Desktop running, Ollama running (for a full read), `git`, `python3`.

## Fast isolated check (recommended: it does not depend on reading your whole real library)
After step 5 has built the images (`./up.sh` made `library-parser:local` and `library:local`), run these with one invented file. They were run on the owner's Mac and passed (see `docs/comment-tracker.md` section 21). Note: the real images start `library-parser` / `library` by themselves, so pass only `--once` to the parser, and `--entrypoint python` to the app image.
```
rm -rf /tmp/o16-in /tmp/o16-out; mkdir -p /tmp/o16-in /tmp/o16-out
printf 'Test report. Marker word ZEBRAQUARTZ. Glucose 5,2 mmol/L.\n' > /tmp/o16-in/t.txt; chmod -R a+rwX /tmp/o16-in /tmp/o16-out
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp -u 10001 -e ATLAS_INBOX=/inbox -e ATLAS_PARSED=/parsed -e LIBRARY_HANDOVER_PUBLIC_KEY="$LIBRARY_HANDOVER_PUBLIC_KEY" -v /tmp/o16-in:/inbox:ro -v /tmp/o16-out:/parsed library-parser:local --once 2>&1 | tail -3
ls -A /tmp/o16-out | grep -v '^\.'      # one <64 hex>.sealed, no .json
grep -rl ZEBRAQUARTZ /tmp/o16-out | wc -l   # 0
cat > /tmp/o16-ingest.py <<'PY'
from pathlib import Path
from kit import db as kdb
from library import store
c = kdb.connect(Path("/data/library.db")); kdb.migrate(c, [store.MODULE])
print("result:", store.ingest_dir(c, Path("/parsed"), on_rejected=lambda *a: print("REJECTED", a[:2])))
print("documents:", [(r[0], r[1][:40]) for r in c.execute("select name, text from documents")])
print("sealed files still on the volume:", len(list(Path("/parsed").glob("*.sealed"))))
PY
run() { docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp --tmpfs /data:uid=10001 -u 10001 --entrypoint python -e ATLAS_DB_KEY=throwaway-test-key-123 -e LIBRARY_HANDOVER_PRIVATE_KEY="$1" -v /tmp/o16-out:/parsed -v /tmp/o16-ingest.py:/ingest.py:ro library:local /ingest.py 2>&1 | tail -4; }
run "0000000000000000000000000000000000000000000000000000000000000000"                              # wrong key: unopened 1, file stays
run "$(security find-generic-password -a "$USER" -s atlas-handover-private -w)"                      # right key: new 1, file removed
```

## 1. Get exactly the commit under review
```
cd ~/path/to/Prasanna            # your clone
git fetch origin atlas && git checkout atlas && git pull --ff-only
git rev-parse HEAD               # must print the full SHA you were told to test
git status --short               # must print nothing
```

## 2. Run the tests natively (author's results become independent ones)
```
python3 -m venv /tmp/atlas-venv && source /tmp/atlas-venv/bin/activate
pip install -e "kit[secure]" -e images -e finance -e "library[dev,parse]" -e atlas pytest pytest-cov pyyaml ruff mypy
(cd library && python -m pytest -q tests/test_seal.py tests/test_sealed_handover.py tests/test_parser_documents.py tests/test_handover.py)
(cd library && python -m pytest -q) ; (cd kit && python -m pytest -q) ; (cd finance && python -m pytest -q) ; (cd atlas && python -m pytest -q) ; (cd images && python -m pytest -q)
```
Expected: no failures (the author saw library 272, kit 165, finance 701, atlas 111, images 100). Paste the last line of each.

**Mutation checks** (each must make exactly the named test fail; restore with `git checkout` after each and confirm `git status --short` prints nothing):
```
# A: always delete, even if the file was replaced after it was read
python3 - <<'PY'
p="library/src/library/store.py"; s=open(p).read()
s=s.replace("            if seen is not None and _identity(f) == seen:\n                f.unlink(missing_ok=True)","            f.unlink(missing_ok=True)",1); open(p,"w").write(s)
PY
(cd library && python -m pytest -q tests/test_handover.py) ; git checkout library/src/library/store.py ; git status --short
# B: the writer does not retry when its temporary file was cleaned up
python3 - <<'PY'
p="library/src/library/batch.py"; s=open(p).read()
s=s.replace("            if last:\n                raise","            raise",1); open(p,"w").write(s)
PY
(cd library && python -m pytest -q tests/test_sealed_handover.py) ; git checkout library/src/library/batch.py ; git status --short
```
Expected: A fails `test_a_result_replaced_after_it_was_read_is_not_deleted_with_the_one_that_was_read`; B fails `test_a_temporary_file_cleaned_up_while_the_reader_was_suspended_is_written_again_not_lost`.

## If Python on the Mac cannot make a virtual environment (for example `ensurepip` fails on Python 3.14)
Skip the local environment and use Docker for steps 2 and 3. Nothing is installed on the Mac:
```
# step 3 replacement: make the keys inside a throw-away container (prints the PRIVATE key, then the PUBLIC key)
docker run --rm -v "$PWD/library/src/library/seal.py:/seal.py:ro" python:3.12-slim sh -c 'pip install -q cryptography >/dev/null 2>&1 && python /seal.py'
# step 2 replacement (library tests only), also in a throw-away container
docker run --rm -v "$PWD":/src -w /src python:3.12-slim sh -c 'pip install -q -e kit -e images -e finance -e "library[dev,parse]" pytest >/dev/null 2>&1; cd library && python -m pytest -q 2>&1 | tail -8'
```
The repository requires Python 3.11 or newer; Python 3.14 is newer than anything the author tested.

## 3. Make the sealing keys (once) and keep the private one in the Keychain
```
source /tmp/atlas-venv/bin/activate        # the environment made in step 2 (if you skipped step 2: python3 -m venv /tmp/atlas-venv && source /tmp/atlas-venv/bin/activate && pip install cryptography)
python3 library/src/library/seal.py        # prints the PRIVATE key, then the PUBLIC key (two lines of 64 characters)
```
Copy the two lines into two shell variables **in this Terminal only** (do not save them in a file or paste them anywhere else):
```
PRIV='<first line>'
PUB='<second line>'
security add-generic-password -a "$USER" -s atlas-handover-private -w "$PRIV" -U
```
Check: `security find-generic-password -a "$USER" -s atlas-handover-private -w | wc -c` prints 65.

## 4. Put one invented test file in the inbox
```
mkdir -p ~/AtlasInbox
printf 'Test report. Marker word ZEBRAQUARTZ. Glucose 5,2 mmol/L (4,0 - 6,0). Datum 12-03-2026.\n' > ~/AtlasInbox/o16-test.txt
```

## 5. Start Atlas with the repository's own scripts, sealing ON
```
export LIBRARY_HANDOVER_PUBLIC_KEY="$PUB"
export LIBRARY_HANDOVER_PRIVATE_KEY="$(security find-generic-password -a "$USER" -s atlas-handover-private -w)"
ATLAS_REBUILD=1 ./up.sh 2>&1 | tail -40
```
This builds the repository's real Dockerfiles (first build takes a while) and starts the real compose files. **Paste the output, and say whether it finished without an error.** If the build fails, paste the first error: that is exactly the thing the author could not test.

## 6. Read the test file
Open http://atlas.localhost:8000, press **Read new files**, wait until it says it is done. Paste the text of the summary card.

## 7. Look inside the shared volume (the point of the whole feature)
```
docker run --rm -v library_library-parsed:/parsed alpine sh -c 'ls -A /parsed; echo "--- readable *.json payloads (must be none):"; ls /parsed/*.json 2>&1; echo "--- the marker word, found in:"; grep -rl ZEBRAQUARTZ /parsed 2>/dev/null; echo "(nothing listed above = not found)"; stat -c "%a %n" /parsed/*.sealed 2>&1'
```
Expected: one `<64 hex>.sealed` file with mode 600 (or none left if Documents already took it in), **no** `<64 hex>.json`, and the marker word found nowhere. Paste everything.

## 8. The document must still arrive
In Atlas ask "Which documents mention ZEBRAQUARTZ?" or open Documents and look for `o16-test.txt`. Say whether it is there. (It needs Ollama for the assistant; the document list does not.)

## 9. A wrong key must lose nothing
```
export LIBRARY_HANDOVER_PRIVATE_KEY="0000000000000000000000000000000000000000000000000000000000000000"
printf 'Second report. Marker word PINEAPPLEFOG.\n' > ~/AtlasInbox/o16-test2.txt
ATLAS_NO_BUILD=1 ./up.sh 2>&1 | tail -3
```
Press **Read new files** again. Expected: the summary says "1 file read but not opened: the key for the sealed hand-over is missing or wrong (nothing was lost, they open once it is right)". Then:
```
docker run --rm -v library_library-parsed:/parsed alpine sh -c 'ls -A /parsed | grep sealed'
```
Expected: the second file's `.sealed` is still there. Now restore the right key and read again:
```
export LIBRARY_HANDOVER_PRIVATE_KEY="$(security find-generic-password -a "$USER" -s atlas-handover-private -w)"
ATLAS_NO_BUILD=1 ./up.sh 2>&1 | tail -3
```
Press **Read new files**: the second file must now be taken in. Paste the summary after each press.

## 10. Container logs and clean up
```
docker compose -f library/docker-compose.yml logs --tail 30 parser app 2>&1 | tail -60
rm ~/AtlasInbox/o16-test.txt ~/AtlasInbox/o16-test2.txt
unset PRIV PUB LIBRARY_HANDOVER_PRIVATE_KEY LIBRARY_HANDOVER_PUBLIC_KEY
```
Delete the two test documents from Atlas if you do not want them kept (Documents page).

## What counts as passing
Steps 2, 5, 7, 8 and 9 all behave as written. Then O-16 can move from PARTIAL to **VERIFIED on the owner's Mac** (the reviewer's P4 still needs a reviewer who ran step 2 themselves). If any step differs, paste the output: that difference is the next thing to fix. Without this run, the alternative is the owner's written acceptance of the plain hand-over.
