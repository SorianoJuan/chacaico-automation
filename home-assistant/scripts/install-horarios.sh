#!/bin/sh
# First install only. Stage public files and a privately merged dashboard beforehand.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
test "$#" -eq 3
stage=$1
expected_config=$2
expected_dashboard=$3
api() { curl -fsS --connect-timeout 10 --max-time 600 -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H 'Content-Type: application/json' "$@"; }
checked() { result=$(api "$@"); printf '%s' "$result" | jq -e '.result == "ok"' >/dev/null; }
api http://supervisor/info | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
test ! -e /config/chacaico-horarios.yaml
! grep -q '^homeassistant:' /config/configuration.yaml
jq -e '.data.config.views | map(select(.path == "horarios")) | length == 1' "$stage/dashboard.json" >/dev/null
backup=/config/chacaico-backups/horarios-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup"
cp -p /config/configuration.yaml "$backup/configuration.yaml"
cp -p /config/.storage/lovelace.dashboard_chacaico "$backup/dashboard.json"
cp -a /local_apps/chacaico_lora_bridge "$backup/bridge"
checked -X POST http://supervisor/backups/new/partial -d '{"name":"Chacaico before daily schedules","addons":["local_chacaico_lora_bridge"],"homeassistant":true}'
printf '%s' "$result" | jq '{result,backup:.data.slug}'
printf '%s' "$result" | jq -er '.data.slug' > "$backup/supervisor-backup-slug"
# Stop Core for the 1GB Pi build AND before changing native storage.
trap 'checked -X POST http://supervisor/core/start || true' EXIT HUP INT TERM
checked -X POST http://supervisor/core/stop
test "$(sha256sum /config/configuration.yaml | cut -d ' ' -f 1)" = "$expected_config"
test "$(sha256sum /config/.storage/lovelace.dashboard_chacaico | cut -d ' ' -f 1)" = "$expected_dashboard"
cp "$stage/engine.py" "$stage/config.yaml" "$stage/Dockerfile" /local_apps/chacaico_lora_bridge/
checked -X POST http://supervisor/store/reload
checked -X POST http://supervisor/addons/local_chacaico_lora_bridge/update
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq -e '.data.version == "0.5.1" and .data.state == "started"' >/dev/null
mkdir -p /config/custom_templates
cp "$stage/chacaico_horarios.jinja" /config/custom_templates/
cp "$stage/chacaico-horarios.yaml" /config/chacaico-horarios.yaml
cat >> /config/configuration.yaml <<'CONFIG'

# BEGIN CHACAICO NATIVE SCHEDULES
homeassistant:
  packages:
    chacaico_horarios: !include chacaico-horarios.yaml
# END CHACAICO NATIVE SCHEDULES
CONFIG
if ! checked -X POST http://supervisor/core/check; then
    cp -p "$backup/configuration.yaml" /config/configuration.yaml
    printf 'Configuration rejected; original configuration restored. Backup: %s\n' "$backup" >&2
    exit 1
fi
cp "$stage/dashboard.json" /config/.storage/lovelace.dashboard_chacaico
checked -X POST http://supervisor/core/start
trap - EXIT HUP INT TERM
printf 'Horarios installed with equal times (no watering) and season disabled. Backup: %s\n' "$backup"
