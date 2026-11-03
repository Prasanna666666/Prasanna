#!/bin/bash
# An encrypted vault for everything Aperture stores about your photos: the index (dates, GPS, places, faces, text, labels, full
# metadata), thumbnails and previews. AES-256, the password lives only in your login Keychain, and nothing readable is left on
# disk when the vault is closed. Your original photos are never copied or changed.
#
#   scripts/aperture-vault.sh create [SIZE_GB]   make the vault (default 60 GB, grows only as needed)
#   scripts/aperture-vault.sh open               mount it at /Volumes/ApertureVault
#   scripts/aperture-vault.sh close              unmount it (data is unreadable again)
#   scripts/aperture-vault.sh migrate OLD_DRIVE  copy an existing Aperture folder into the vault (does NOT delete the old one)
#
# Then run Aperture with:  APERTURE_DRIVE=/Volumes/ApertureVault aperture secure-ui
set -euo pipefail

BUNDLE="${APERTURE_VAULT_FILE:-$HOME/ApertureVault.sparsebundle}"
MOUNT="/Volumes/ApertureVault"
SERVICE="aperture-vault"

password() { security find-generic-password -s "$SERVICE" -a "$USER" -w 2>/dev/null; }

case "${1:-}" in
  create)
    size="${2:-60}"
    [ -e "$BUNDLE" ] && { echo "$BUNDLE already exists"; exit 1; }
    pw="$(openssl rand -base64 36)"
    security add-generic-password -U -s "$SERVICE" -a "$USER" -w "$pw"   # stored in the Keychain, never printed or written to a file
    printf '%s' "$pw" | hdiutil create -size "${size}g" -type SPARSEBUNDLE -fs APFS -encryption AES-256 -stdinpass \
        -volname ApertureVault "$BUNDLE"
    echo "created $BUNDLE (encrypted). Next: $0 open"
    ;;
  open)
    pw="$(password)" || { echo "no vault password in the Keychain"; exit 1; }
    printf '%s' "$pw" | hdiutil attach "$BUNDLE" -stdinpass -nobrowse -mountpoint "$MOUNT" >/dev/null
    mkdir -p "$MOUNT/Aperture" && chmod 700 "$MOUNT" "$MOUNT/Aperture"
    echo "open at $MOUNT. Run: APERTURE_DRIVE=$MOUNT aperture secure-ui"
    ;;
  close)
    hdiutil detach "$MOUNT" && echo "closed: the data is unreadable until you open it again"
    ;;
  migrate)
    old="${2:?usage: $0 migrate OLD_DRIVE   (for example /Volumes/Expansion)}"
    [ -d "$old/Aperture" ] || { echo "no $old/Aperture folder"; exit 1; }
    [ -d "$MOUNT" ] || { echo "open the vault first"; exit 1; }
    rsync -a --info=progress2 "$old/Aperture/" "$MOUNT/Aperture/"
    echo "copied. After you have checked that Aperture works from the vault, remove the old copy yourself:"
    echo "  rm -r \"$old/Aperture\"   (it is unencrypted)"
    ;;
  *)
    sed -n '2,13p' "$0"; exit 2 ;;
esac
