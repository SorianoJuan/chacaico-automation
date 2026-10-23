#!/bin/sh
# Run through LAN SSH after authorizing HTTPS certificates and Funnel for this Pi.
# Publishes only the Home Assistant HTTPS endpoint; preserves other Tailscale options.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 180 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H 'Content-Type: application/json' "$@"
}
checked_api() {
    chacaico_response=$(api "$@") || return $?
    printf '%s' "$chacaico_response" | jq -es 'length == 1 and .[0].result == "ok"' >/dev/null
}
api http://supervisor/info | jq -e \
    '.result == "ok" and .data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
# HTTP is managed through HA's UI in Core2026.9; do not edit .storage while running.
jq -e '.data.pending == null and .data.stable.server_port == 80
    and .data.stable.use_x_forwarded_for == true
    and .data.stable.trusted_proxies == ["127.0.0.1/32"]' /config/.storage/http >/dev/null
chacaico_backup=/config/chacaico-backups/funnel-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
api http://supervisor/addons/a0d7b954_tailscale/info > "$chacaico_backup/tailscale-before.json"
jq -e '.result == "ok" and .data.state == "started"
    and .data.options.share_homeassistant == "disabled"
    and .data.options.services == []' "$chacaico_backup/tailscale-before.json" >/dev/null
jq '{options:.data.options}' "$chacaico_backup/tailscale-before.json" > "$chacaico_backup/restore.json"
jq '{options:(.data.options + {share_homeassistant:"funnel",share_on_port:"443"})}' \
    "$chacaico_backup/tailscale-before.json" > "$chacaico_backup/request.json"
cp -p /config/.storage/http "$chacaico_backup/http.json"
sha256sum /config/configuration.yaml /config/chacaico-controls.yaml /config/.storage/lovelace.dashboard_chacaico > "$chacaico_backup/unchanged.sha256"
chacaico_modified=false
recover() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0 && test "$chacaico_modified" = true; then
        checked_api -X POST --data-binary @"$chacaico_backup/restore.json" \
            http://supervisor/addons/a0d7b954_tailscale/options || true
        checked_api -X POST http://supervisor/addons/a0d7b954_tailscale/restart || true
        printf 'Funnel activation failed; prior options restoration attempted. Backup: %s\n' "$chacaico_backup" >&2
    fi
    exit "$chacaico_exit"
}
trap recover EXIT
trap 'exit 130' HUP INT TERM
chacaico_modified=true
checked_api -X POST --data-binary @"$chacaico_backup/request.json" http://supervisor/addons/a0d7b954_tailscale/options
checked_api -X POST http://supervisor/addons/a0d7b954_tailscale/restart
sleep 5
api http://supervisor/addons/a0d7b954_tailscale/info | jq -e --slurpfile target "$chacaico_backup/request.json" \
    '.result == "ok" and .data.state == "started" and .data.options == $target[0].options' >/dev/null
sha256sum -c "$chacaico_backup/unchanged.sha256"
printf 'Funnel option enabled; verify public HTTPS, authentication, WebSocket and private SSH. Backup: %s\n' "$chacaico_backup"
trap - EXIT HUP INT TERM
