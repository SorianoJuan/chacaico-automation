#!/bin/sh
# Run in Terminal & SSH after copying chacaico-valves.yaml to /tmp.
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
test -s /tmp/chacaico-valves.yaml
chacaico_backup=/config/chacaico-backups/valve-panel-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
cp -p /config/configuration.yaml "$chacaico_backup/configuration.yaml"
chacaico_had_panel=false
if test -e /config/chacaico-valves.yaml; then
    cp -p /config/chacaico-valves.yaml "$chacaico_backup/chacaico-valves.yaml"
    chacaico_had_panel=true
fi
chacaico_modified=false
recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0 && test "$chacaico_modified" = true; then
        cp -p "$chacaico_backup/configuration.yaml" /config/configuration.yaml
        if test "$chacaico_had_panel" = true; then
            cp -p "$chacaico_backup/chacaico-valves.yaml" /config/chacaico-valves.yaml
        else
            rm -f /config/chacaico-valves.yaml
        fi
        checked_api -X POST http://supervisor/core/start || true
        printf 'Restored dashboard configuration; backup: %s\n' "$chacaico_backup" >&2
    fi
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM
if ! grep -qx '# BEGIN CHACAICO VALVE PANEL' /config/configuration.yaml; then
    if grep -q '^lovelace:' /config/configuration.yaml; then
        printf '%s\n' 'Existing Lovelace configuration needs an explicit merge.' >&2
        exit 1
    fi
    chacaico_modified=true
    cat >> /config/configuration.yaml <<'CONFIG'

# BEGIN CHACAICO VALVE PANEL
lovelace:
  mode: storage
  dashboards:
    chacaico-valves:
      mode: yaml
      title: Chacaico
      icon: mdi:valve
      show_in_sidebar: true
      filename: chacaico-valves.yaml
# END CHACAICO VALVE PANEL
CONFIG
fi
chacaico_modified=true
cp /tmp/chacaico-valves.yaml /config/chacaico-valves.yaml
# The app update below stops Core before building/checking, to limit RAM use.
checked_api -X POST http://supervisor/core/stop
checked_api -X POST http://supervisor/core/check
printf 'Panel validated. Backup: %s\n' "$chacaico_backup"
printf '%s\n' 'Core remains stopped; run install-local-app.sh next to update the bridge and start Core.'
trap - EXIT HUP INT TERM
