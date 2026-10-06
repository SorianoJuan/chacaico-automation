#!/bin/sh
# Remove only the original YAML dashboard; preserve UI-managed dashboards and controls.
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

chacaico_backup=/config/chacaico-backups/remove-yaml-dashboard-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
cat > "$chacaico_backup/expected-panel.txt" <<'PANEL'
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
PANEL
awk '/^# BEGIN CHACAICO VALVE PANEL$/{show=1} show{print} /^# END CHACAICO VALVE PANEL$/{show=0}' \
    /config/configuration.yaml > "$chacaico_backup/actual-panel.txt"
cmp -s "$chacaico_backup/expected-panel.txt" "$chacaico_backup/actual-panel.txt" || {
    printf '%s\n' 'Unexpected dashboard block; refusing to modify configuration.' >&2
    exit 1
}
test -s /config/chacaico-valves.yaml
test -s /config/chacaico-controls.yaml
jq -e '.data.items[] | select(.id == "dashboard_chacaico" and .url_path == "dashboard-chacaico" and .mode == "storage")' \
    /config/.storage/lovelace_dashboards >/dev/null
cp -p /config/configuration.yaml "$chacaico_backup/configuration.yaml"
cp -p /config/chacaico-valves.yaml "$chacaico_backup/chacaico-valves.yaml"
sha256sum /config/chacaico-controls.yaml > "$chacaico_backup/controls.sha256"
chacaico_modified=false
chacaico_stopped=false
recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0; then
        if test "$chacaico_modified" = true; then
            cp -p "$chacaico_backup/configuration.yaml" /config/configuration.yaml
            cp -p "$chacaico_backup/chacaico-valves.yaml" /config/chacaico-valves.yaml
        fi
        if test "$chacaico_stopped" = true; then
            checked_api -X POST http://supervisor/core/start || true
        fi
        printf 'Recovered configuration after failure; backup: %s\n' "$chacaico_backup" >&2
    fi
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM
chacaico_stopped=true
checked_api -X POST http://supervisor/core/stop
# Capture after Core has flushed storage; never edit or restore UI dashboards.
for chacaico_file in /config/.storage/lovelace*; do
    if test -f "$chacaico_file"; then
        sha256sum "$chacaico_file"
    fi
done > "$chacaico_backup/ui-dashboards.sha256"
# Refuse to overwrite a configuration edited since the initial read.
cmp -s /config/configuration.yaml "$chacaico_backup/configuration.yaml"
awk '
    /^# BEGIN CHACAICO VALVE PANEL$/ {
        skip=1
        print "# Dashboards managed from the Home Assistant UI."
        print "lovelace:"
        print "  mode: storage"
        next
    }
    /^# END CHACAICO VALVE PANEL$/ {skip=0; next}
    !skip {print}
' /config/configuration.yaml > "$chacaico_backup/configuration-ui.yaml"
chacaico_modified=true
cp "$chacaico_backup/configuration-ui.yaml" /config/configuration.yaml
rm /config/chacaico-valves.yaml
checked_api -X POST http://supervisor/core/check
sha256sum -c "$chacaico_backup/controls.sha256"
sha256sum -c "$chacaico_backup/ui-dashboards.sha256"
checked_api -X POST http://supervisor/core/start
sha256sum -c "$chacaico_backup/controls.sha256"
sha256sum -c "$chacaico_backup/ui-dashboards.sha256"
chacaico_stopped=false
printf 'YAML dashboard removed; UI dashboards preserved. Backup: %s\n' "$chacaico_backup"
trap - EXIT HUP INT TERM
