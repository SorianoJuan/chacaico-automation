#!/bin/sh
# Install a local app while Core is stopped to reduce the Docker build peak.
set -eu
: "${SUPERVISOR_TOKEN:?}"
test "$#" -gt 0
for chacaico_slug in "$@"; do
    case "$chacaico_slug" in local_chacaico_*) ;; *) exit 1 ;; esac
done
api() {
    curl -fsS --connect-timeout 10 --max-time 600 \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H 'Content-Type: application/json' "$@"
}
checked_api() {
    chacaico_response=$(api "$@") || return $?
    printf '%s' "$chacaico_response" | jq -es 'length == 1 and .[0].result == "ok"' >/dev/null
}
chacaico_info=$(api http://supervisor/info)
printf '%s' "$chacaico_info" | jq -e '.data.machine_id == "2e21da3405714e0cba2d890984d6dfa8"' >/dev/null
checked_api -X POST http://supervisor/store/reload
trap 'checked_api -X POST http://supervisor/core/start || true' EXIT HUP INT TERM
checked_api -X POST http://supervisor/core/stop
for chacaico_slug in "$@"; do
    printf 'Installing %s with Core stopped.\n' "$chacaico_slug"
    chacaico_app=$(api "http://supervisor/addons/$chacaico_slug/info")
    if printf '%s' "$chacaico_app" | jq -e '.data.version != null' >/dev/null; then
        checked_api -X POST "http://supervisor/addons/$chacaico_slug/update"
    else
        checked_api -X POST "http://supervisor/addons/$chacaico_slug/install"
    fi
done
checked_api -X POST http://supervisor/core/start
trap - EXIT HUP INT TERM
printf '%s\n' 'App installed; Core restarted.'
