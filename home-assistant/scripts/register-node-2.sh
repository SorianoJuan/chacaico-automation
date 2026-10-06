#!/bin/sh
# Run after copying ignored bridge-options.json to /tmp/chacaico-bridge-options.json.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 300 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H 'Content-Type: application/json' "$@"
}
checked_api() {
    chacaico_response=$(api "$@") || return $?
    printf '%s' "$chacaico_response" | jq -es 'length == 1 and .[0].result == "ok"' >/dev/null
}
api http://supervisor/info | jq -e \
    '.result == "ok" and .data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
chacaico_input=/tmp/chacaico-bridge-options.json
test -s "$chacaico_input"
jq -e '(.options.nodes | map(.id) | sort) == [1,2]
    and (.options.nodes | map(.key | ascii_downcase) | unique | length) == 2
    and (.options.nodes | all(.key | test("^[0-9a-fA-F]{32}$")))
    and .options.self_test == false' "$chacaico_input" >/dev/null
chacaico_backup=/config/chacaico-backups/register-node-2-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq '.data.options' \
    > "$chacaico_backup/bridge-options-before.json"
# Verify node 1's identity/frequency against the live Pi; preserve unrelated options.
jq -e --slurpfile target "$chacaico_input" '
    (.nodes | map(.id) | sort) == [1]
    and .frequency == $target[0].options.frequency
    and ([.nodes[] | select(.id == 1)] == [$target[0].options.nodes[] | select(.id == 1)])
' "$chacaico_backup/bridge-options-before.json" >/dev/null
jq --slurpfile target "$chacaico_input" '{options:(. + $target[0].options)}' \
    "$chacaico_backup/bridge-options-before.json" > "$chacaico_backup/request.json"
jq '{options:.}' "$chacaico_backup/bridge-options-before.json" > "$chacaico_backup/restore.json"
chacaico_stopped=false
chacaico_modified=false
recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0; then
        if test "$chacaico_modified" = true; then
            checked_api -X POST --data-binary @"$chacaico_backup/restore.json" \
                http://supervisor/addons/local_chacaico_lora_bridge/options || true
        fi
        if test "$chacaico_stopped" = true; then
            checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/start || true
        fi
        printf 'Recovered bridge after failure; backup: %s\n' "$chacaico_backup" >&2
    fi
    rm -f "$chacaico_input"
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM
chacaico_stopped=true
checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/stop
chacaico_modified=true
checked_api -X POST --data-binary @"$chacaico_backup/request.json" \
    http://supervisor/addons/local_chacaico_lora_bridge/options
checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/start
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq -e --slurpfile target "$chacaico_input" \
    '.result == "ok" and .data.state == "started"
     and .data.options.nodes == $target[0].options.nodes and .data.options.self_test == false' >/dev/null
chacaico_stopped=false
printf 'Nodes 1 and 2 registered; node 1 identity preserved. Backup: %s\n' "$chacaico_backup"
