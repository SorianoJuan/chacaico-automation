#!/bin/sh
# Private credentials stay on the Pi. This helper never accepts valve commands.
set -eu
: "${SUPERVISOR_TOKEN:?}"
curl -fsS -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/info | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
entry=$(jq -ce '[.data.entries[] | select(.domain == "mqtt")][0].data' /config/.storage/core.config_entries)
host=$(printf '%s' "$entry" | jq -er .broker)
port=$(printf '%s' "$entry" | jq -er .port)
user=$(printf '%s' "$entry" | jq -er .username)
password=$(printf '%s' "$entry" | jq -er .password)
case "$1" in
 sub) exec mosquitto_sub -h "$host" -p "$port" -u "$user" -P "$password" -q 1 -t 'chacaico/lora/#' -F '%t\t%p' ;;
 pub)
  case "$2" in
   chacaico/lora/bridge/power/set|chacaico/lora/bridge/power/apply|chacaico/lora/node/[12]/led/set|chacaico/lora/node/[12]/config/*|chacaico/lora/node/[12]/policy/*) ;;
   *) echo 'Topic refused by bench helper' >&2; exit 1 ;;
  esac
  exec mosquitto_pub -h "$host" -p "$port" -u "$user" -P "$password" -q 1 -t "$2" -m "$3" ;;
 *) exit 1 ;;
esac
