#!/bin/sh
# Run inside Terminal & SSH. All credential-bearing files stay on the Pi.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?Run inside Terminal & SSH}"

chacaico_new_config=/tmp/chacaico-configuration-minimal.yaml
chacaico_backup=/config/chacaico-backups/minimal-$(date -u +%Y%m%dT%H%M%SZ)-$$
chacaico_modified=false
chacaico_stopped=false

api() {
    curl --fail --silent --show-error --connect-timeout 10 --max-time 300 \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        -H 'Content-Type: application/json' "$@"
}

checked_api() {
    chacaico_reply=$(api "$@") || return $?
    if ! printf '%s' "$chacaico_reply" |
        jq -es 'length == 1 and .[0].result == "ok"' >/dev/null; then
        printf '%s' "$chacaico_reply" | jq '{result, message}' >&2
        return 1
    fi
}

recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if [ "$chacaico_exit" -ne 0 ]; then
        if [ "$chacaico_modified" = true ]; then
            if checked_api -X POST http://supervisor/core/stop; then
                cp -p "$chacaico_backup/configuration.yaml" /config/configuration.yaml
                cp -p "$chacaico_backup/core.config_entries" /config/.storage/core.config_entries
                printf '%s\n' 'Restored the saved configuration after failure.' >&2
            else
                printf 'Could not safely restore; backup: %s\n' "$chacaico_backup" >&2
            fi
        fi
        if [ "$chacaico_stopped" = true ]; then
            checked_api -X POST http://supervisor/core/start || true
        fi
    fi
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM

chacaico_info=$(api http://supervisor/info)
printf '%s' "$chacaico_info" | jq -e '
    .result == "ok" and
    .data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"
' >/dev/null
test -s "$chacaico_new_config"
jq -e '.key == "core.config_entries" and (.data.entries | type) == "array"' \
    /config/.storage/core.config_entries >/dev/null

mkdir -p "$chacaico_backup"
api http://supervisor/core/stats > "$chacaico_backup/core-stats-before.json"
cp /proc/meminfo "$chacaico_backup/meminfo-before.txt"

# Stop Core before changing its storage so it cannot overwrite our edits.
chacaico_stopped=true
checked_api -X POST http://supervisor/core/stop
cp -p /config/configuration.yaml "$chacaico_backup/configuration.yaml"
cp -p /config/.storage/core.config_entries "$chacaico_backup/core.config_entries"

chacaico_disabled_domains='["bluetooth","go2rtc","thread","cast","google_translate","met","radio_browser","shopping_list","sun"]'
jq --argjson domains "$chacaico_disabled_domains" '
    .data.entries |= map(
        if (.domain as $domain | $domains | index($domain)) != null
           and .source != "ignore" and .disabled_by == null
        then .disabled_by = "user"
        else . end
    )
' "$chacaico_backup/core.config_entries" > /config/.storage/core.config_entries.chacaico-tmp
jq -e '.key == "core.config_entries" and (.data.entries | type) == "array"' \
    /config/.storage/core.config_entries.chacaico-tmp >/dev/null

chacaico_modified=true
cp "$chacaico_new_config" /config/configuration.yaml
mv /config/.storage/core.config_entries.chacaico-tmp /config/.storage/core.config_entries

# The built-in check runs with Core stopped, keeping memory demand lower.
checked_api -X POST http://supervisor/core/check
checked_api -X POST http://supervisor/core/start
chacaico_stopped=false

printf 'Backup: %s\n' "$chacaico_backup"
jq '[.data.entries[] | select(.disabled_by == "user") | .domain]' \
    /config/.storage/core.config_entries
trap - EXIT HUP INT TERM
