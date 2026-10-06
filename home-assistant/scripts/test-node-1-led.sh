#!/bin/sh
# Radio/MQTT verification: LED commands only; never publishes a valve command.
set -eu
umask 077
: "${SUPERVISOR_TOKEN:?}"
api() {
    curl -fsS --connect-timeout 10 --max-time 20 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" "$@"
}
api http://supervisor/info | jq -e \
    '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
api http://supervisor/addons/local_chacaico_lora_bridge/info | jq -e \
    '(.data.options.nodes | map(.id) | sort) == [1,2] and .data.options.self_test == false' >/dev/null
chacaico_mqtt_entry=$(jq -ce '[.data.entries[] | select(.domain == "mqtt")][0].data' /config/.storage/core.config_entries)
chacaico_mqtt_host=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.broker')
chacaico_mqtt_port=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.port')
chacaico_mqtt_user=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.username')
chacaico_mqtt_password=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.password')
mqtt_pub() {
    mosquitto_pub -h "$chacaico_mqtt_host" -p "$chacaico_mqtt_port" \
        -u "$chacaico_mqtt_user" -P "$chacaico_mqtt_password" -q 1 "$@"
}
read_status() {
    mosquitto_sub -h "$chacaico_mqtt_host" -p "$chacaico_mqtt_port" \
        -u "$chacaico_mqtt_user" -P "$chacaico_mqtt_password" \
        -q 1 -C 1 -W 5 -t chacaico/lora/node/1/status
}
cleanup() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test "$chacaico_exit" -ne 0; then
        mqtt_pub -t chacaico/lora/node/1/led/set -m OFF || true
    fi
    exit "$chacaico_exit"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
send_led() {
    chacaico_before=$(read_status | jq -er '.sequence')
    mqtt_pub -t chacaico/lora/node/1/led/set -m "$1"
    chacaico_expected=$2
    chacaico_attempt=0
    while test "$chacaico_attempt" -lt 12; do
        sleep 1
        chacaico_status=$(read_status)
        if printf '%s' "$chacaico_status" | jq -e --argjson before "$chacaico_before" \
            --argjson expected "$chacaico_expected" \
            '.node == 1 and .sequence > $before and .led == $expected' >/dev/null; then
            printf '%s' "$chacaico_status"
            return
        fi
        chacaico_attempt=$((chacaico_attempt + 1))
    done
    printf '%s\n' 'No fresh LED acknowledgment from node 1.' >&2
    return 1
}
chacaico_on=$(send_led ON true)
chacaico_on_sequence=$(printf '%s' "$chacaico_on" | jq -er '.sequence')
# With only node 1 connected, an OFF addressed to node 2 must not change node 1.
mqtt_pub -t chacaico/lora/node/2/led/set -m OFF
chacaico_attempt=0
chacaico_isolated=false
while test "$chacaico_attempt" -lt 15; do
    sleep 5
    chacaico_logs=$(api http://supervisor/addons/local_chacaico_lora_bridge/logs)
    chacaico_get=$(printf '%s\n' "$chacaico_logs" | awk -v baseline="$chacaico_on_sequence" '
        /ACK node=1 / && / op=0 value=1 / {
            for (i=1;i<=NF;i++) if ($i ~ /^sequence=/) {
                split($i,a,"="); if (a[2] > baseline) latest=$0
            }
        }
        END {print latest}
    ')
    chacaico_no_ack=$(printf '%s\n' "$chacaico_logs" | awk -v baseline="$chacaico_on_sequence" '
        /No ACK from node=2 / {
            for (i=1;i<=NF;i++) if ($i ~ /^sequence=/) {
                split($i,a,"="); if (a[2] > baseline) latest=$0
            }
        }
        END {print latest}
    ')
    if test -n "$chacaico_get" && test -n "$chacaico_no_ack"; then
        chacaico_isolated=true
        break
    fi
    chacaico_attempt=$((chacaico_attempt + 1))
done
test "$chacaico_isolated" = true || {
    printf '%s\n' 'Did not observe a fresh GET_LED ON after the node 2 OFF command.' >&2
    exit 1
}
chacaico_off=$(send_led OFF false)
jq -n --argjson on "$chacaico_on" --argjson off "$chacaico_off" \
    --arg get "$chacaico_get" --arg no_ack "$chacaico_no_ack" '{
    passed:true, node:1, led_on:$on, led_off:$off,
    isolation:{command:"LED OFF addressed to node 2", node_2_no_ack:$no_ack,
               node_1_fresh_get_led_still_on:$get},
    valve_commands_sent:false, final_led:"OFF"
}' > /config/chacaico-node-1-test.json
cat /config/chacaico-node-1-test.json
