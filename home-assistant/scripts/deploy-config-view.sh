#!/bin/sh
# Run inside Terminal & SSH with staged public app files and a privately merged dashboard.
set -eu
: "${SUPERVISOR_TOKEN:?}"
test "$#" -eq 3
chacaico_stage=$1
chacaico_view=$2
chacaico_expected=$3
chacaico_storage=/config/.storage/lovelace.dashboard_chacaico
api() { curl -fsS --connect-timeout 10 --max-time 600 -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H 'Content-Type: application/json' "$@"; }
checked() { chacaico_result=$(api "$@"); printf '%s' "$chacaico_result" | jq -e '.result == "ok"' >/dev/null; }
api http://supervisor/info | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
test -f "$chacaico_stage/engine.py"
jq -e '.key == "lovelace.dashboard_chacaico" and (.data.config.views | map(select(.path == "configuracion-lora")) | length == 1)' "$chacaico_view" >/dev/null
chacaico_backup=/config/chacaico-backups/config-v050-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$chacaico_backup"
chmod 700 "$chacaico_backup"
cp -a /local_apps/chacaico_lora_bridge "$chacaico_backup/bridge"
checked -X POST http://supervisor/backups/new/partial -d '{"name":"Chacaico before configuration v0.5.0","addons":["local_chacaico_lora_bridge"],"homeassistant":true}'
printf '%s' "$chacaico_result" | jq '{result,backup:.data.slug}'
chacaico_backup_slug=$(printf '%s' "$chacaico_result" | jq -er '.data.slug')
api "http://supervisor/backups/$chacaico_backup_slug/info" | jq -e '.result == "ok" and .data.homeassistant != null and (.data.addons | length > 0)' >/dev/null
printf '%s\n' 'Backup complete; stopping Core for the app build.'
trap 'checked -X POST http://supervisor/core/start || true' EXIT HUP INT TERM
checked -X POST http://supervisor/core/stop
test "$(sha256sum "$chacaico_storage" | cut -d ' ' -f 1)" = "$chacaico_expected"
cp -p "$chacaico_storage" "$chacaico_backup/dashboard.json"
cp "$chacaico_stage/bridge.py" "$chacaico_stage/engine.py" "$chacaico_stage/protocol.py" "$chacaico_stage/radio.py" "$chacaico_stage/Dockerfile" "$chacaico_stage/config.yaml" /local_apps/chacaico_lora_bridge/
checked -X POST http://supervisor/store/reload
checked -X POST http://supervisor/addons/local_chacaico_lora_bridge/update
cp "$chacaico_view" "$chacaico_storage.tmp"
chmod 600 "$chacaico_storage.tmp"
mv "$chacaico_storage.tmp" "$chacaico_storage"
checked -X POST http://supervisor/core/start
trap - EXIT HUP INT TERM
printf 'Deployment finished; private backup: %s\n' "$chacaico_backup"
