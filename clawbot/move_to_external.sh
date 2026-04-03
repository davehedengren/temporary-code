#!/bin/bash
# Move completed downloads to external drive. Run via cron or manually.
SRC="$HOME/code/clawbot/download_staging"
DST="/Volumes/Elements/AER_replication_data"

mkdir -p "$DST"
count=0
for f in "$SRC"/*.zip; do
    [ -f "$f" ] || continue
    mv "$f" "$DST/" && count=$((count + 1))
done
echo "Moved $count files to external drive"
