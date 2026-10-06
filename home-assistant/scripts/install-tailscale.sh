#!/bin/sh
# Community prebuilt app; preserves normal SSH and current HA network/DNS.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
chacaico_slug=a0d7b954_tailscale
api() {
    curl -fsS --connect-timeout 10 --max-time 600 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H 'Content-Type: application/json' "$@"
}
checked_api() {
    chacaico_response=$(api "$@") || return $?
    printf '%s' "$chacaico_response" | jq -es 'length == 1 and .[0].result == "ok"' >/dev/null
}
api http://supervisor/info | jq -e \
    '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
chacaico_backup=/config/chacaico-backups/tailscale-$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$chacaico_backup"
api http://supervisor/store/addons/$chacaico_slug | jq -e \
    '.result == "ok" and .data.slug == "a0d7b954_tailscale" and .data.installed == false' >/dev/null
for chacaico_file in /config/.storage/lovelace*; do
    if test -f "$chacaico_file"; then sha256sum "$chacaico_file"; fi
done > "$chacaico_backup/ui.sha256"
sha256sum /config/configuration.yaml /config/chacaico-controls.yaml > "$chacaico_backup/ha.sha256"
api http://supervisor/addons/core_ssh/info | jq '.data.options' > "$chacaico_backup/ssh-options.json"
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq '.data.options' > "$chacaico_backup/bridge-options.json"
checked_api -X POST http://supervisor/addons/$chacaico_slug/install
api http://supervisor/addons/$chacaico_slug/info | jq '.data.options' > "$chacaico_backup/tailscale-defaults.json"
jq '{boot:"auto",watchdog:true,options:(. + {
    accept_dns:false,accept_routes:false,advertise_connector:false,
    advertise_exit_node:false,advertise_routes:[],advertise_tags:[],
    share_homeassistant:"disabled",services:[],taildrop:false,
    userspace_networking:false
})}' "$chacaico_backup/tailscale-defaults.json" > "$chacaico_backup/request.json"
checked_api -X POST --data-binary @"$chacaico_backup/request.json" http://supervisor/addons/$chacaico_slug/options
checked_api -X POST http://supervisor/addons/$chacaico_slug/start
api http://supervisor/addons/$chacaico_slug/info | jq '{
    state:.data.state,version:.data.version,boot:.data.boot,watchdog:.data.watchdog,
    protected:.data.protected,full_access:.data.full_access,
    accept_dns:.data.options.accept_dns,accept_routes:.data.options.accept_routes,
    advertise_routes:.data.options.advertise_routes,userspace_networking:.data.options.userspace_networking,
    share_homeassistant:.data.options.share_homeassistant,ingress_url:.data.ingress_url
}'
sha256sum -c "$chacaico_backup/ui.sha256"
sha256sum -c "$chacaico_backup/ha.sha256"
printf '%s\n' "$chacaico_backup" > /tmp/chacaico-tailscale-backup-path
printf 'Tailscale installed; complete account login in its Web UI. Backup: %s\n' "$chacaico_backup"
