# Your folders had Orbit in their names. Each is renamed once (same disk, nothing copied or changed inside), and the old name stays as a link, so nothing that points at it breaks.
for pair in OrbitInbox:AtlasInbox OrbitFinance:AtlasFinance; do
  old="$HOME/${pair%%:*}"; new="$HOME/${pair##*:}"
  if [ -d "$old" ] && [ ! -L "$old" ] && [ ! -e "$new" ]; then
    mv "$old" "$new" && ln -s "${pair##*:}" "$old" && echo "Renamed ~/${pair%%:*} to ~/${pair##*:} (the old name still works as a link)."
  fi
done
