#!/bin/sh
# Upload only a verified build for the explicit node and physical USB port.
set -eu
chacaico_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$chacaico_script_dir/.."
test "$#" -eq 3 && test "$1" = '--id' || {
    printf '%s\n' 'Usage: sh firmware/flash-node.sh --id N /dev/serial/by-path/<physical-port>' >&2
    exit 1
}
chacaico_node=$2
case "$chacaico_node" in ''|*[!0-9]*) exit 1 ;; esac
chacaico_port=$3
case "$chacaico_port" in
    /dev/serial/by-path/*-port0) ;;
    *) printf '%s\n' 'Select a physical by-path port; CP2102 serial numbers may be duplicated.' >&2; exit 1 ;;
esac
chacaico_build="firmware/nodes/node_$chacaico_node/build"
python3 firmware/verify-build.py --id "$chacaico_node"
test -c "$chacaico_port"
test -r "$chacaico_port" && test -w "$chacaico_port"
udevadm info --query=property --name="$chacaico_port" | grep -qx 'ID_VENDOR_ID=10c4'
udevadm info --query=property --name="$chacaico_port" | grep -qx 'ID_MODEL_ID=ea60'
exec arduino-cli upload --config-file .tools/arduino-cli.yaml \
    --fqbn CubeCell:CubeCell:CubeCell-Board:LORAWAN_REGION=2,LORAWAN_AT_SUPPORT=1,LORAWAN_RGB=1 \
    --input-dir "$chacaico_build" --port "$chacaico_port" "firmware/nodes/node_$chacaico_node"
