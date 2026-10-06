#!/bin/sh
set -eu
umask 077
/opt/lora/bin/python /probe-sx1262.py > /config/probe.json.tmp
mv /config/probe.json.tmp /config/probe.json
cat /config/probe.json
