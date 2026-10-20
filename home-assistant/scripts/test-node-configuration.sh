#!/bin/sh
# Explicit bench test: both antennas connected; modifies config/LED, never a valve.
# Run in Terminal & SSH: sh test-node-configuration.sh --bench
set -eu
test "$#" -eq 1 && test "$1" = --bench || { echo 'Usage: sh test-node-configuration.sh --bench' >&2; exit 1; }
set -eu
: "${SUPERVISOR_TOKEN:?}"
api() { curl -fsS --connect-timeout 10 --max-time 60 -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H 'Content-Type: application/json' "$@"; }
api http://supervisor/info | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
chacaico_entry=$(jq -ce '[.data.entries[] | select(.domain == "mqtt")][0].data' /config/.storage/core.config_entries)
chacaico_host=$(printf '%s' "$chacaico_entry" | jq -er '.broker')
chacaico_port=$(printf '%s' "$chacaico_entry" | jq -er '.port')
chacaico_user=$(printf '%s' "$chacaico_entry" | jq -er '.username')
chacaico_password=$(printf '%s' "$chacaico_entry" | jq -er '.password')
pub() { mosquitto_pub -h "$chacaico_host" -p "$chacaico_port" -u "$chacaico_user" -P "$chacaico_password" -q 1 -t "chacaico/lora/node/$1/$2" -m "$3"; }
sub() { mosquitto_sub -h "$chacaico_host" -p "$chacaico_port" -u "$chacaico_user" -P "$chacaico_password" -q 1 "$@"; }
read_topic() { sub -C 1 -W 5 -t "chacaico/lora/node/$1/$2"; }
wait_cfg() {
 chacaico_node=$1;chacaico_sleep=$2;chacaico_pulse=$3;chacaico_count=0
 while test "$chacaico_count" -lt 45; do
  chacaico_cfg=$(read_topic "$chacaico_node" config/reported)
  if printf '%s' "$chacaico_cfg" | jq -e --argjson s "$chacaico_sleep" --argjson p "$chacaico_pulse" '.sleep_s == $s and .pulse_ms == $p' >/dev/null; then printf '%s\n' "$chacaico_cfg";return;fi
  sleep 1;chacaico_count=$((chacaico_count+1))
 done
 printf 'Timed out confirming node %s\n' "$chacaico_node" >&2;return 1
}

api http://supervisor/addons/local_chacaico_lora_bridge/info | jq -e '(.data.version | IN("0.4.0", "0.4.1", "0.4.2", "0.4.3")) and .data.state == "started"' >/dev/null
# Refuse to overwrite an existing field setup. This fixture starts at 0s/50ms, LED off.
for n in 1 2; do
 read_topic "$n" config/reported | jq -e '.sleep_s == 0 and .pulse_ms == 50' >/dev/null
 test "$(read_topic "$n" led/state)" = OFF
done
restore() {
 for n in 1 2; do
  pub "$n" led/set OFF || true
  pub "$n" config/sleep_s/set 0 || true
  pub "$n" config/pulse_ms/set 50 || true
  pub "$n" config/apply APPLY || true
 done
}
trap 'restore' EXIT
for n in 1 2; do
 chacaico_before=$(read_topic "$n" config/reported | jq -r '.revision')
 pub "$n" config/sleep_s/set "$((n*2+3))"
 pub "$n" config/pulse_ms/set "$((n*10+50))"
 sleep 1
 read_topic "$n" config/reported | jq -e --argjson rev "$chacaico_before" '.revision == $rev and .sleep_s == 0 and .pulse_ms == 50' >/dev/null
 pub "$n" config/apply APPLY
 wait_cfg "$n" "$((n*2+3))" "$((n*10+50))"
 chacaico_revision=$(read_topic "$n" config/reported | jq -r '.revision')
 pub "$n" config/apply APPLY
 pub "$n" config/query QUERY
 sleep 12
 read_topic "$n" config/reported | jq -e --argjson rev "$chacaico_revision" '.revision == $rev' >/dev/null
 pub "$n" led/set ON
 chacaico_attempt=0
 while test "$(read_topic "$n" led/state)" != ON; do
  sleep 1;chacaico_attempt=$((chacaico_attempt+1));test "$chacaico_attempt" -lt 25
 done
 test "$(read_topic "$((3-n))" led/state)" = OFF
 pub "$n" led/set OFF
 chacaico_attempt=0
 while test "$(read_topic "$n" led/state)" != OFF; do
  sleep 1;chacaico_attempt=$((chacaico_attempt+1));test "$chacaico_attempt" -lt 25
 done
 printf 'PASS node %s draft, apply, duplicate, query, sleeping LED and isolation\n' "$n"
done
restore
wait_cfg 1 0 50
wait_cfg 2 0 50
trap - EXIT
printf '%s\n' 'PASS defaults restored; no valve commands sent'
