#!/bin/sh
# Both nodes awake/connected: sustained LED traffic, status checks, no valve commands.
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
    '.data.state == "started" and .data.version == "0.3.0"
     and (.data.options.nodes | map(.id) | sort) == [1,2] and .data.options.self_test == false' >/dev/null
chacaico_mqtt_entry=$(jq -ce '[.data.entries[] | select(.domain == "mqtt")][0].data' /config/.storage/core.config_entries)
chacaico_mqtt_host=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.broker')
chacaico_mqtt_port=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.port')
chacaico_mqtt_user=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.username')
chacaico_mqtt_password=$(printf '%s' "$chacaico_mqtt_entry" | jq -er '.password')
mqtt_pub() {
    mosquitto_pub -h "$chacaico_mqtt_host" -p "$chacaico_mqtt_port" \
        -u "$chacaico_mqtt_user" -P "$chacaico_mqtt_password" -q 1 "$@"
}
mqtt_sub() {
    mosquitto_sub -h "$chacaico_mqtt_host" -p "$chacaico_mqtt_port" \
        -u "$chacaico_mqtt_user" -P "$chacaico_mqtt_password" -q 1 "$@"
}
read_topic() { mqtt_sub -C 1 -W 5 -t "$1"; }
chacaico_testdir=$(mktemp -d /tmp/chacaico-polling-test.XXXXXX)
chacaico_monitor_pid=
chacaico_original_1=
chacaico_original_2=
cleanup() {
    chacaico_exit=$?
    trap - EXIT HUP INT TERM
    if test -n "$chacaico_monitor_pid"; then
        kill "$chacaico_monitor_pid" 2>/dev/null || true
        wait "$chacaico_monitor_pid" 2>/dev/null || true
    fi
    if test "$chacaico_exit" -ne 0; then
        case "$chacaico_original_1" in ON|OFF) mqtt_pub -t chacaico/lora/node/1/led/set -m "$chacaico_original_1" || true ;; esac
        case "$chacaico_original_2" in ON|OFF) mqtt_pub -t chacaico/lora/node/2/led/set -m "$chacaico_original_2" || true ;; esac
    fi
    rm -rf "$chacaico_testdir"
    exit "$chacaico_exit"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
for chacaico_node in 1 2; do
    test "$(read_topic "chacaico/lora/node/$chacaico_node/valve/availability")" = online
    read_topic "chacaico/lora/node/$chacaico_node/valve/status" > "$chacaico_testdir/valve-before-$chacaico_node.json"
    read_topic "chacaico/lora/node/$chacaico_node/valve/state" > "$chacaico_testdir/valve-state-before-$chacaico_node"
done
chacaico_original_1=$(read_topic chacaico/lora/node/1/led/state)
chacaico_original_2=$(read_topic chacaico/lora/node/2/led/state)
case "$chacaico_original_1:$chacaico_original_2" in ON:ON|ON:OFF|OFF:ON|OFF:OFF) ;; *) exit 1 ;; esac
mqtt_sub -R -v -W 360 -t chacaico/lora/node/1/valve/availability \
    -t chacaico/lora/node/2/valve/availability > "$chacaico_testdir/availability.log" 2>/dev/null &
chacaico_monitor_pid=$!
chacaico_started=$(date +%s)
chacaico_step=0
: > "$chacaico_testdir/acks.jsonl"
while test "$chacaico_step" -lt 20; do
    if test "$((chacaico_step % 2))" -eq 0; then chacaico_value=ON; chacaico_bool=true
    else chacaico_value=OFF; chacaico_bool=false; fi
    for chacaico_node in 1 2; do
        read_topic "chacaico/lora/node/$chacaico_node/status" | jq -er '.sequence' \
            > "$chacaico_testdir/before-$chacaico_node"
        mqtt_pub -t "chacaico/lora/node/$chacaico_node/led/set" -m "$chacaico_value"
    done
    sleep 5
    for chacaico_node in 1 2; do
        chacaico_status=$(read_topic "chacaico/lora/node/$chacaico_node/status")
        printf '%s' "$chacaico_status" | jq -e --argjson node "$chacaico_node" \
            --argjson before "$(cat "$chacaico_testdir/before-$chacaico_node")" --argjson expected "$chacaico_bool" \
            '.node == $node and .sequence > $before and .led == $expected' >/dev/null
        printf '%s\n' "$chacaico_status" >> "$chacaico_testdir/acks.jsonl"
        test "$(read_topic "chacaico/lora/node/$chacaico_node/valve/availability")" = online
    done
    chacaico_step=$((chacaico_step + 1))
done
chacaico_finished=$(date +%s)
kill "$chacaico_monitor_pid" 2>/dev/null || true
wait "$chacaico_monitor_pid" 2>/dev/null || true
chacaico_monitor_pid=
! grep -q '/valve/availability offline' "$chacaico_testdir/availability.log"
for chacaico_node in 1 2; do
    read_topic "chacaico/lora/node/$chacaico_node/valve/status" > "$chacaico_testdir/valve-after-$chacaico_node.json"
    read_topic "chacaico/lora/node/$chacaico_node/valve/state" > "$chacaico_testdir/valve-state-after-$chacaico_node"
    cmp -s "$chacaico_testdir/valve-state-before-$chacaico_node" "$chacaico_testdir/valve-state-after-$chacaico_node"
    jq -e --slurpfile before "$chacaico_testdir/valve-before-$chacaico_node.json" \
        --argjson now "$chacaico_finished" \
        '.sequence > $before[0].sequence and ($now - .confirmed_at) < 75' \
        "$chacaico_testdir/valve-after-$chacaico_node.json" >/dev/null
done
mqtt_pub -t chacaico/lora/node/1/led/set -m "$chacaico_original_1"
mqtt_pub -t chacaico/lora/node/2/led/set -m "$chacaico_original_2"
sleep 2
test "$(read_topic chacaico/lora/node/1/led/state)" = "$chacaico_original_1"
test "$(read_topic chacaico/lora/node/2/led/state)" = "$chacaico_original_2"
jq -n --argjson started "$chacaico_started" --argjson finished "$chacaico_finished" \
    --slurpfile acks "$chacaico_testdir/acks.jsonl" \
    --slurpfile before1 "$chacaico_testdir/valve-before-1.json" --slurpfile after1 "$chacaico_testdir/valve-after-1.json" \
    --slurpfile before2 "$chacaico_testdir/valve-before-2.json" --slurpfile after2 "$chacaico_testdir/valve-after-2.json" \
    --arg led1 "$chacaico_original_1" --arg led2 "$chacaico_original_2" '{
    passed:true, bridge_version:"0.3.0", duration_seconds:($finished-$started),
    led_command_checks:($acks|length), valve_availability_stayed_online:true,
    valve_state_unchanged:true, valve_commands_sent:false,
    nodes:[{id:1,valve_before:$before1[0],valve_after:$after1[0],led_restored:$led1},
           {id:2,valve_before:$before2[0],valve_after:$after2[0],led_restored:$led2}]
}' > /config/chacaico-bridge-polling-test.json
cat /config/chacaico-bridge-polling-test.json
