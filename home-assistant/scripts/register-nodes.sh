#!/bin/sh
# Add explicit IDs from ignored bridge-options.json without replacing existing identities.
# Usage on the verified Pi: sh register-nodes.sh 3 4
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
test "$#" -gt 0
for chacaico_id in "$@"; do
    case "$chacaico_id" in ''|*[!0-9]*) exit 1 ;; esac
    test "$chacaico_id" -ge 1 && test "$chacaico_id" -le 65534
done
chacaico_ids=$(jq -cn --args '$ARGS.positional | map(tonumber) | unique' "$@")
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
jq -e '.options as $o | ($o.nodes | length) as $n |
    $n > 0 and ($o.nodes | map(.id) | unique | length) == $n
    and ($o.nodes | all(.id >= 1 and .id <= 65534 and .id == (.id | floor)))
    and ($o.nodes | map(.key | ascii_downcase) | unique | length) == $n
    and ($o.nodes | all(.key | test("^[0-9a-fA-F]{32}$")))
    and $o.self_test == false' "$chacaico_input" >/dev/null
chacaico_backup=/config/chacaico-backups/register-nodes-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq -e '.result == "ok" and .data.state == "started"' >/dev/null
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq '.data.options' > "$chacaico_backup/bridge-options-before.json"
# Only explicitly requested IDs may be added; every existing ID/key must match exactly.
jq -e --argjson added "$chacaico_ids" --slurpfile target "$chacaico_input" '
    . as $old | $target[0].options as $new |
    ((($old.nodes | map(.id)) + $added | unique | sort) == ($new.nodes | map(.id) | sort))
    and $old.frequency == $new.frequency
    and all($old.nodes[]; . as $node | any($new.nodes[]; . == $node))
' "$chacaico_backup/bridge-options-before.json" >/dev/null
jq --slurpfile target "$chacaico_input" '{options:(. + {nodes:$target[0].options.nodes,self_test:false})}' \
    "$chacaico_backup/bridge-options-before.json" > "$chacaico_backup/request.json"
jq '{options:.}' "$chacaico_backup/bridge-options-before.json" > "$chacaico_backup/restore.json"
chacaico_stopped=false
chacaico_modified=false
recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0; then
        if test "$chacaico_modified" = true; then
            checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/stop || true
            checked_api -X POST --data-binary @"$chacaico_backup/restore.json" \
                http://supervisor/addons/local_chacaico_lora_bridge/options || true
        fi
        if test "$chacaico_stopped" = true; then
            checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/start || true
        fi
        printf 'Registration failed; restoration attempted. Inspect backup: %s\n' "$chacaico_backup" >&2
    fi
    rm -f "$chacaico_input"
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM
chacaico_stopped=true
checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/stop
chacaico_modified=true
checked_api -X POST --data-binary @"$chacaico_backup/request.json" http://supervisor/addons/local_chacaico_lora_bridge/options
checked_api -X POST http://supervisor/addons/local_chacaico_lora_bridge/start
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq -e --slurpfile target "$chacaico_backup/request.json" \
    '.result == "ok" and .data.state == "started" and .data.options == $target[0].options' >/dev/null
chacaico_stopped=false
printf 'Registered requested nodes %s; existing keys/options preserved. Backup: %s\n' "$chacaico_ids" "$chacaico_backup"
