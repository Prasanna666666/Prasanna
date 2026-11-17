#!/bin/bash
# Source this from library/scripts/up.sh (run from the library folder). Decides whether what the reader hands to the store is SEALED, and says so in one plain line.
# Sealed means: the reader holds only a PUBLIC key and can write results it can never read back; only the store holds the PRIVATE key. The keys live in the macOS Keychain
# (made once, on first use). It never starts with half a configuration: a public key without a private key would pile up results nothing can open.
#   ATLAS_SEAL_HANDOVER=0   turn sealing off (the hand-over is then plain text between the two containers, as before)
#   ATLAS_REQUIRE_SEALED=1  refuse to start if sealing cannot be turned on, instead of starting plain
SEAL_PRIV_SERVICE="${SEAL_PRIV_SERVICE:-atlas-handover-private}"
SEAL_PUB_SERVICE="${SEAL_PUB_SERVICE:-atlas-handover-public}"
SEAL_PY="${HANDOVER_SEAL_PY:-$PWD/src/library/seal.py}"

_seal_plain() {   # $1 = why. Starts plain, loudly, unless sealing was required.
  if [ "${ATLAS_REQUIRE_SEALED:-}" = 1 ]; then echo "Sealed hand-over: cannot be turned on ($1), and ATLAS_REQUIRE_SEALED=1: not starting." >&2; return 2; fi
  export LIBRARY_HANDOVER_PUBLIC_KEY="" LIBRARY_HANDOVER_PRIVATE_KEY=""
  echo "Sealed hand-over: OFF ($1). The text of what is read is handed over unsealed between the reader and the store until this is fixed."
}
_seal_is_key() { [[ "$1" =~ ^[0-9a-f]{64}$ ]]; }

_seal_decide() {
  if [ "${ATLAS_SEAL_HANDOVER:-1}" = 0 ]; then _seal_plain "turned off with ATLAS_SEAL_HANDOVER=0"; return; fi
  local pub="${LIBRARY_HANDOVER_PUBLIC_KEY:-}" priv="${LIBRARY_HANDOVER_PRIVATE_KEY:-}"
  if [ -n "$pub" ] || [ -n "$priv" ]; then   # given in the environment: both or neither
    if [ -z "$pub" ] || [ -z "$priv" ]; then echo "Sealed hand-over: only one of LIBRARY_HANDOVER_PUBLIC_KEY / LIBRARY_HANDOVER_PRIVATE_KEY is set. Set both, or neither. Not starting." >&2; return 2; fi
    if ! _seal_is_key "$pub" || ! _seal_is_key "$priv"; then echo "Sealed hand-over: a key in the environment is not 64 hexadecimal characters. Not starting." >&2; return 2; fi
    export LIBRARY_HANDOVER_PUBLIC_KEY="$pub" LIBRARY_HANDOVER_PRIVATE_KEY="$priv"; echo "Sealed hand-over: ON (keys from the environment)."; return
  fi
  command -v security >/dev/null 2>&1 || { _seal_plain "needs the macOS Keychain; or set both LIBRARY_HANDOVER_* keys"; return; }
  pub="$(security find-generic-password -a "$USER" -s "$SEAL_PUB_SERVICE" -w 2>/dev/null || true)"
  priv="$(security find-generic-password -a "$USER" -s "$SEAL_PRIV_SERVICE" -w 2>/dev/null || true)"
  if [ -n "$pub" ] && [ -n "$priv" ]; then
    if ! _seal_is_key "$pub" || ! _seal_is_key "$priv"; then echo "Sealed hand-over: the keys in the Keychain ($SEAL_PUB_SERVICE, $SEAL_PRIV_SERVICE) are not 64 hexadecimal characters. Not starting." >&2; return 2; fi
    export LIBRARY_HANDOVER_PUBLIC_KEY="$pub" LIBRARY_HANDOVER_PRIVATE_KEY="$priv"; echo "Sealed hand-over: ON (keys from the Keychain)."; return
  fi
  if [ -z "$pub" ] && [ -n "$priv" ] && _seal_is_key "$priv"; then   # only the private key is kept: the public one is worked out from it and kept too
    pub="$(docker run --rm -v "$SEAL_PY:/seal.py:ro" python:3.12-slim sh -c "pip install -q cryptography >/dev/null 2>&1 && python /seal.py --public-from-private $priv" 2>/dev/null | head -1 || true)"
    if _seal_is_key "$pub" && security add-generic-password -a "$USER" -s "$SEAL_PUB_SERVICE" -w "$pub" -U; then
      export LIBRARY_HANDOVER_PUBLIC_KEY="$pub" LIBRARY_HANDOVER_PRIVATE_KEY="$priv"; echo "Sealed hand-over: ON (keys from the Keychain; the public key was worked out from the private one)."; return
    fi
    _seal_plain "the public key could not be worked out from the private key in the Keychain (Docker needs the internet once)"; return
  fi
  if [ -n "$pub" ] || [ -n "$priv" ]; then   # the public key alone (or a damaged private one): never guess, never start plain behind the person's back
    echo "Sealed hand-over: the Keychain holds only the public key, or a private key that is not 64 hexadecimal characters ($SEAL_PUB_SERVICE, $SEAL_PRIV_SERVICE). Delete the one that is there (security delete-generic-password -a \"\$USER\" -s <name>) so a new pair can be made. Not starting." >&2; return 2
  fi
  # neither exists: make a pair once, in a throw-away container (the host Python may lack the package), keep both in the Keychain
  local made
  made="$(docker run --rm -v "$SEAL_PY:/seal.py:ro" python:3.12-slim sh -c 'pip install -q cryptography >/dev/null 2>&1 && python /seal.py' 2>/dev/null || true)"
  priv="$(printf '%s\n' "$made" | sed -n 1p)"; pub="$(printf '%s\n' "$made" | sed -n 2p)"
  if ! _seal_is_key "$priv" || ! _seal_is_key "$pub"; then _seal_plain "no key pair could be made (Docker needs the internet once to make it)"; return; fi
  security add-generic-password -a "$USER" -s "$SEAL_PRIV_SERVICE" -w "$priv" -U && security add-generic-password -a "$USER" -s "$SEAL_PUB_SERVICE" -w "$pub" -U \
    || { _seal_plain "the keys could not be stored in the Keychain"; return; }
  export LIBRARY_HANDOVER_PUBLIC_KEY="$pub" LIBRARY_HANDOVER_PRIVATE_KEY="$priv"; echo "Sealed hand-over: ON (a new key pair was made and kept in the Keychain)."
}
_seal_decide
