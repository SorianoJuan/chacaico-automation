#!/bin/sh
# Run in Terminal & SSH with chacaico-controls.yaml copied to /tmp.
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
test -s /tmp/chacaico-controls.yaml
if grep -q '^template:' /config/configuration.yaml &&
   ! grep -qx 'template: !include chacaico-controls.yaml' /config/configuration.yaml; then
    printf '%s\n' 'Existing template configuration needs an explicit merge.' >&2
    exit 1
fi
chacaico_backup=/config/chacaico-backups/control-switches-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
cp -p /config/configuration.yaml "$chacaico_backup/configuration.yaml"
chacaico_had_controls=false
if test -e /config/chacaico-controls.yaml; then
    cp -p /config/chacaico-controls.yaml "$chacaico_backup/chacaico-controls.yaml"
    chacaico_had_controls=true
fi
chacaico_modified=false
chacaico_stopped=false
recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0; then
        if test "$chacaico_modified" = true; then
            cp -p "$chacaico_backup/configuration.yaml" /config/configuration.yaml
            if test "$chacaico_had_controls" = true; then
                cp -p "$chacaico_backup/chacaico-controls.yaml" /config/chacaico-controls.yaml
            else
                rm -f /config/chacaico-controls.yaml
            fi
        fi
        if test "$chacaico_stopped" = true; then
            checked_api -X POST http://supervisor/core/start || true
        fi
        printf 'Recovered original configuration after failure; backup: %s\n' "$chacaico_backup" >&2
    fi
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM
chacaico_stopped=true
checked_api -X POST http://supervisor/core/stop
chacaico_modified=true
cp /tmp/chacaico-controls.yaml /config/chacaico-controls.yaml
if ! grep -qx 'template: !include chacaico-controls.yaml' /config/configuration.yaml; then
    cat >> /config/configuration.yaml <<'CONFIG'

# BEGIN CHACAICO CONTROL SWITCHES
template: !include chacaico-controls.yaml
# END CHACAICO CONTROL SWITCHES
CONFIG
fi
checked_api -X POST http://supervisor/core/check
checked_api -X POST http://supervisor/core/start
chacaico_stopped=false
printf 'Valve/LED switches configured; Core restarted. Backup: %s\n' "$chacaico_backup"
trap - EXIT HUP INT TERM
