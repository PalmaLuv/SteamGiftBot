#!/usr/bin/env bash
# Daily copy of what the bot farm cannot rebuild: panel password, site
# cookies and settings (farm.json, config.ini) and history, seen ids and
# daily counters (botfarm-state.json, steamgiftbot-state.json).
# The archive holds live cookies, so it is readable by the owner only.
# cron: 27 4 * * * /opt/SteamGiftBot/scripts/backup-farm.sh
# KEEP=N sets how many archives stay (default 14).
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
mkdir -p backups
files=()
for name in farm.json botfarm-state.json config.ini steamgiftbot-state.json; do
  [ -f "$name" ] && files+=("$name")
done
archive="backups/botfarm-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$archive" "${files[@]}"
echo "$(date '+%F %T') Готово: $archive ($(du -h "$archive" | cut -f1))"

keep="${KEEP:-14}"
ls -1t backups/botfarm-*.tar.gz 2>/dev/null | tail -n +"$((keep + 1))" | xargs -r rm -f --
