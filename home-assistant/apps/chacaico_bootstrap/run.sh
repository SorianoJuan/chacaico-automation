#!/bin/sh
# One-time local setup. No credentials leave this app.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 60 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H 'Content-Type: application/json' "$@"
}
chacaico_info=$(api http://supervisor/info)
printf '%s' "$chacaico_info" | jq -e '
    .result == "ok" and
    .data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"
' >/dev/null

# Use Home Assistant's supported configuration flow, without reading passwords.
chacaico_entries=$(api http://supervisor/core/api/config/config_entries/entry)
if ! printf '%s' "$chacaico_entries" | jq -e 'any(.[]; .domain == "mqtt")' >/dev/null; then
    chacaico_flow=$(api -X POST --data '{"handler":"mqtt","show_advanced_options":false}' \
        http://supervisor/core/api/config/config_entries/flow)
    printf '%s' "$chacaico_flow" | jq -e '
        .type == "menu" and .step_id == "user" and (.menu_options | index("addon")) != null
    ' >/dev/null
    chacaico_flow_id=$(printf '%s' "$chacaico_flow" | jq -r '.flow_id')
    chacaico_flow=$(api -X POST --data '{"next_step_id":"addon"}' \
        "http://supervisor/core/api/config/config_entries/flow/$chacaico_flow_id")
    printf '%s' "$chacaico_flow" | jq -e '.type == "create_entry"' >/dev/null
    printf '%s\n' 'MQTT integration configured with the installed Mosquitto app.'
fi

# Mount only the identified boot partition; preserve an exact config backup.
ls -l /dev/mmcblk0p1
chacaico_boot_info=$(blkid /dev/mmcblk0p1) || {
    printf '%s\n' 'Could not inspect the boot device.' >&2
    exit 1
}
chacaico_boot_label=$(printf '%s' "$chacaico_boot_info" | sed -n 's/.*LABEL="\([^"]*\)".*/\1/p')
chacaico_boot_uuid=$(printf '%s' "$chacaico_boot_info" | sed -n 's/.*UUID="\([^"]*\)".*/\1/p')
printf 'Boot label: %s\n' "$chacaico_boot_label"
test "$chacaico_boot_label" = 'hassos-boot'
test "$chacaico_boot_uuid" = 'A833-5627'
mkdir -p /boot-config
mount -t vfat -o rw /dev/mmcblk0p1 /boot-config
trap 'umount /boot-config' EXIT HUP INT TERM
test -s /boot-config/config.txt
chacaico_backup=/config/config-before-spi-$(date -u +%Y%m%dT%H%M%SZ).txt
cp /boot-config/config.txt "$chacaico_backup"
cp /boot-config/config.txt /tmp/chacaico-config.txt
printf '\n# Chacaico Waveshare SX1262 HAT\n[all]\ndtparam=spi=on\n' >> /tmp/chacaico-config.txt
cp /tmp/chacaico-config.txt /boot-config/config.txt.chacaico-new
sync
mv /boot-config/config.txt.chacaico-new /boot-config/config.txt
sync
cmp /tmp/chacaico-config.txt /boot-config/config.txt
umount /boot-config
trap - EXIT HUP INT TERM
printf 'SPI enabled. Boot configuration backup: %s\n' "$chacaico_backup"
printf '%s\n' '{"spi_enabled":true,"mqtt_configured":true,"reboot_required":true}' > /config/result.json
