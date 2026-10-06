#!/bin/sh
# Execute the manually unlocked one-time app, then remove its hardware access.
set -eu
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 90 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H 'Content-Type: application/json' "$@"
}
checked_api() {
    chacaico_response=$(api "$@") || return $?
    printf '%s' "$chacaico_response" | jq -es 'length == 1 and .[0].result == "ok"' >/dev/null
}
chacaico_info=$(api http://supervisor/info)
printf '%s' "$chacaico_info" | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
chacaico_app=$(api http://supervisor/addons/local_chacaico_bootstrap/info)
printf '%s' "$chacaico_app" | jq -e '
    .data.slug == "local_chacaico_bootstrap" and
    .data.full_access == true and
    .data.version == "0.1.4" and
    .data.boot_config == "manual_only" and
    .data.protected == false
' >/dev/null
cleanup() {
    checked_api -X POST http://supervisor/addons/local_chacaico_bootstrap/stop || true
}
trap cleanup EXIT HUP INT TERM
checked_api -X POST http://supervisor/addons/local_chacaico_bootstrap/start
chacaico_attempt=0
while [ ! -s /app_configs/local_chacaico_bootstrap/result.json ] && [ "$chacaico_attempt" -lt 30 ]; do
    sleep 1
    chacaico_attempt=$((chacaico_attempt + 1))
done
api http://supervisor/addons/local_chacaico_bootstrap/logs/latest
jq -e '.spi_enabled == true and .mqtt_configured == true' \
    /app_configs/local_chacaico_bootstrap/result.json
mkdir -p /config/chacaico-backups/boot-spi
cp /app_configs/local_chacaico_bootstrap/config-before-spi-*.txt \
    /config/chacaico-backups/boot-spi/
cleanup
checked_api -X POST http://supervisor/addons/local_chacaico_bootstrap/uninstall
trap - EXIT HUP INT TERM
