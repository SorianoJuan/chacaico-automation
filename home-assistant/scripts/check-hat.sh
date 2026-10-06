#!/bin/sh
set -eu
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 60 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" "$@"
}
chacaico_attempt=0
while :; do
    chacaico_info=$(api http://supervisor/info)
    printf '%s' "$chacaico_info" | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
    if printf '%s' "$chacaico_info" | jq -e '.data.state == "running"' >/dev/null; then break; fi
    chacaico_attempt=$((chacaico_attempt + 1))
    test "$chacaico_attempt" -lt 20
    sleep 2
done
chacaico_app=$(api http://supervisor/addons/local_chacaico_lora_probe/info)
printf '%s' "$chacaico_app" | jq -e '
    .data.protected == true and .data.full_access == false and
    .data.devices == ["/dev/spidev0.0", "/dev/gpiochip0"]
' >/dev/null
if [ -s /app_configs/local_chacaico_lora_probe/probe.json ]; then
    mv /app_configs/local_chacaico_lora_probe/probe.json \
        /app_configs/local_chacaico_lora_probe/probe.previous.json
fi
chacaico_reply=$(api -X POST http://supervisor/addons/local_chacaico_lora_probe/start)
printf '%s' "$chacaico_reply" | jq -e '.result == "ok"' >/dev/null
chacaico_attempt=0
while [ ! -s /app_configs/local_chacaico_lora_probe/probe.json ] && [ "$chacaico_attempt" -lt 15 ]; do
    sleep 1
    chacaico_attempt=$((chacaico_attempt + 1))
done
api http://supervisor/addons/local_chacaico_lora_probe/logs/latest
jq -e '.spi_verified == true and .rf_transmitted == false' \
    /app_configs/local_chacaico_lora_probe/probe.json >/dev/null
cat /app_configs/local_chacaico_lora_probe/probe.json
