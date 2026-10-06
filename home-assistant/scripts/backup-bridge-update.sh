#!/bin/sh
# Snapshot this Pi's source/options and UI hashes before updating the local bridge.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 20 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" "$@"
}
api http://supervisor/info | jq -e \
    '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
chacaico_backup=/config/chacaico-backups/bridge-polling-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq '.data.options' \
    > "$chacaico_backup/bridge-options.json"
jq -e '(.nodes | map(.id) | sort) == [1,2] and .self_test == false' \
    "$chacaico_backup/bridge-options.json" >/dev/null
tar -C /local_apps -cf "$chacaico_backup/bridge-source.tar" chacaico_lora_bridge
for chacaico_file in /config/.storage/lovelace*; do
    if test -f "$chacaico_file"; then sha256sum "$chacaico_file"; fi
done > "$chacaico_backup/ui.sha256"
sha256sum /config/chacaico-controls.yaml > "$chacaico_backup/controls.sha256"
printf '%s\n' "$chacaico_backup" > /tmp/chacaico-bridge-update-backup-path
printf 'Bridge source/options backed up: %s\n' "$chacaico_backup"
