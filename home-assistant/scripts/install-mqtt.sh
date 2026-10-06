#!/bin/sh
# Run inside Terminal & SSH on the new Chacaico Pi.
# Supervisor credentials remain inside the app; never enable shell tracing.
set -eu

: "${SUPERVISOR_TOKEN:?Run this script inside the HAOS Terminal & SSH app}"
command -v curl >/dev/null
command -v jq >/dev/null

api() {
    curl --fail --silent --show-error --connect-timeout 10 --max-time 300 \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        -H 'Content-Type: application/json' "$@"
}

expect_ok() {
    jq -es 'length == 1 and .[0].result == "ok"' >/dev/null
}

checked_api() {
    chacaico_reply=$(api "$@") || return $?
    printf '%s' "$chacaico_reply" | expect_ok
}

# Refuse to configure another Home Assistant installation.
info=$(api http://supervisor/info)
printf '%s' "$info" | jq -e '
    .result == "ok" and
    .data.machine == "raspberrypi5-64" and
    .data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"
' >/dev/null || {
    printf '%s\n' 'Target identity does not match the new Chacaico Pi.' >&2
    exit 1
}

apps=$(api http://supervisor/addons)
printf '%s' "$apps" | expect_ok
if ! printf '%s' "$apps" | jq -e '
    any(.data.addons[]; .slug == "core_mosquitto")
' >/dev/null; then
    checked_api -X POST http://supervisor/addons/core_mosquitto/install
fi

# Keep the app configuration and credentials already present.
checked_api -X POST --data '{"boot":"auto","watchdog":true}' \
    http://supervisor/addons/core_mosquitto/options

app=$(api http://supervisor/addons/core_mosquitto/info)
printf '%s' "$app" | expect_ok
if ! printf '%s' "$app" | jq -e '.data.state == "started"' >/dev/null; then
    checked_api -X POST http://supervisor/addons/core_mosquitto/start
fi

api http://supervisor/addons/core_mosquitto/info | jq -e '
    if .result == "ok" and .data.state == "started" then
        .data | {slug, version, state, boot, watchdog}
    else error("Mosquitto did not start") end
'
