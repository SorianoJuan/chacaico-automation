#!/usr/bin/env python3
"""Home Assistant MQTT discovery and acknowledged LoRa LED/valve control."""
import json
import logging
import os
from pathlib import Path
import queue
import secrets
import signal
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

from protocol import encode, decode, GET_LED, SET_LED, GET_VALVE, SET_VALVE, VALVE_UNKNOWN
from radio import Radio

LOG = logging.getLogger("chacaico")
ROOT = "chacaico/lora"
POLL_INTERVAL = 60
OFFLINE_TIMEOUT = 90
COMMAND_TTL = 15
ACK_TIMEOUT = 1
MAX_TRIES = 3


def mqtt_service():
    request = urllib.request.Request("http://supervisor/services/mqtt", headers={
        "Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if data.get("result") != "ok":
        raise RuntimeError("Supervisor MQTT service is unavailable")
    return data["data"]


class Bridge:
    def __init__(self, options, radio):
        self.radio = radio
        self.nodes = {n["id"]: bytes.fromhex(n["key"]) for n in options["nodes"]}
        if any(len(key) != 16 for key in self.nodes.values()):
            raise ValueError("Each node must have a 16-byte authentication key")
        self.commands = queue.Queue(maxsize=32)
        self.stop = threading.Event()
        self.pending = None
        self.seen = {}
        self.valve_seen = {}
        self.status = {}
        self.last_ack = {}
        self.next_poll = {(node, operation): 0 for node in self.nodes
                          for operation in (GET_VALVE, GET_LED)}
        self.last_was_poll = False
        self.counter_file = Path("/config/sequence.json")
        self.sequence = json.loads(self.counter_file.read_text()) if self.counter_file.exists() else secrets.randbelow(1 << 30)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="chacaico-lora-bridge")
        self.client.will_set(ROOT + "/bridge/availability", "offline", qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = lambda *args: LOG.warning("MQTT disconnected") if not self.stop.is_set() else None
        service = mqtt_service()
        self.client.username_pw_set(service["username"], service["password"])
        if service.get("ssl"):
            self.client.tls_set()
        self.client.connect(service["host"], service["port"], 30)
        self.client.loop_start()

    def publish(self, topic, payload):
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        return self.client.publish(topic, payload, qos=1, retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("MQTT connection rejected: %s", reason_code)
            return
        for node in self.nodes:
            base = f"{ROOT}/node/{node}"
            device = {"identifiers": [f"chacaico_cubecell_{node}"], "name": f"CubeCell {node}",
                      "manufacturer": "Heltec", "model": "HTCC-AB01", "sw_version": "chacaico-valve-0.3.0"}
            common = {"device": device, "availability_mode": "all", "availability": [
                {"topic": ROOT + "/bridge/availability"}, {"topic": base + "/availability"}]}
            self.publish(f"homeassistant/switch/chacaico_node_{node}/led/config", {
                **common, "name": "LED de prueba", "unique_id": f"chacaico_node_{node}_led",
                "state_topic": base + "/led/state", "command_topic": base + "/led/set",
                "payload_on": "ON", "payload_off": "OFF", "qos": 1, "retain": False,
                "icon": "mdi:led-on", "json_attributes_topic": base + "/status"})
            self.publish(f"homeassistant/valve/chacaico_node_{node}/valve/config", {
                **common, "name": "Electroválvula", "unique_id": f"chacaico_node_{node}_valve",
                "default_entity_id": f"valve.chacaico_node_{node}",
                "availability": [{"topic": ROOT + "/bridge/availability"},
                                 {"topic": base + "/valve/availability"}],
                "state_topic": base + "/valve/state", "command_topic": base + "/valve/set",
                "payload_open": "OPEN", "payload_close": "CLOSE", "optimistic": False,
                "qos": 1, "retain": False, "icon": "mdi:valve",
                "json_attributes_topic": base + "/valve/status"})
            self.publish(base + "/valve/state", "None")
            self.publish(base + "/valve/availability", "offline")
            # A broker reconnect also needs a fresh valve response, immediately.
            self.next_poll[(node, GET_VALVE)] = 0
            for field, unit, name in (("rssi", "dBm", "RSSI"), ("snr", "dB", "SNR")):
                self.publish(f"homeassistant/sensor/chacaico_node_{node}/{field}/config", {
                    **common, "name": name, "unique_id": f"chacaico_node_{node}_{field}",
                    "state_topic": base + "/status", "value_template": "{{ value_json." + field + " }}",
                    "unit_of_measurement": unit, "state_class": "measurement", "entity_category": "diagnostic"})
            self.publish(base + "/availability", "online" if node in self.seen and time.monotonic() - self.seen[node] < OFFLINE_TIMEOUT else "offline")
            client.subscribe(base + "/led/set", qos=1)
            client.subscribe(base + "/valve/set", qos=1)
        self.publish(ROOT + "/bridge/availability", "online")
        LOG.info("MQTT connected; discovery published for %s", sorted(self.nodes))

    def on_message(self, client, userdata, message):
        if message.retain:
            LOG.warning("Ignored retained command")
            return
        try:
            parts = message.topic.split("/")
            if len(parts) != 6 or parts[:3] != ["chacaico", "lora", "node"] or parts[5] != "set":
                return
            node = int(parts[3])
            payload = message.payload.decode("ascii")
            if node not in self.nodes:
                return
            if parts[4] == "led" and payload in ("ON", "OFF"):
                operation, value = SET_LED, int(payload == "ON")
            elif parts[4] == "valve" and payload in ("OPEN", "CLOSE"):
                operation, value = SET_VALVE, int(payload == "OPEN")
            else:
                return
            self.commands.put_nowait((node, operation, value, time.monotonic()))
        except (ValueError, UnicodeError, queue.Full):
            LOG.warning("Invalid command or command queue full")

    def next_request(self, now):
        due = [key for key, deadline in self.next_poll.items() if deadline <= now]
        poll = min(due, key=lambda key: (self.next_poll[key],
                   0 if key[1] == GET_VALVE else 1, key[0])) if due else None
        # Alternate a due query and a user command when both are waiting.
        # Neither a busy command queue nor offline peers may monopolize the radio.
        if poll and not self.last_was_poll:
            self.last_was_poll = True
            return (*poll, 0)
        while True:
            try:
                node, operation, value, queued_at = self.commands.get_nowait()
            except queue.Empty:
                break
            if now - queued_at <= COMMAND_TTL:
                self.last_was_poll = False
                return node, operation, value
            LOG.warning("Expired queued command for node=%d", node)
        if poll:
            self.last_was_poll = True
            return (*poll, 0)
        return None

    def start_request(self, node, operation, value, now=None):
        if now is None:
            now = time.monotonic()
        if operation in (GET_LED, GET_VALVE):
            # Also advance failed polls, independently of the other status type.
            self.next_poll[(node, operation)] = now + POLL_INTERVAL
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        temporary = self.counter_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.sequence))
        temporary.replace(self.counter_file)
        self.pending = {"node": node, "seq": self.sequence, "op": operation, "value": value,
                        "frame": encode(self.nodes[node], 0, node, self.sequence, operation, value), "tries": 0, "next": 0}
        if operation == SET_VALVE:
            self.publish(f"{ROOT}/node/{node}/valve/status", {
                "sequence": self.sequence, "command": "OPEN" if value else "CLOSE",
                "confirmation": "pending", "state_source": "gpio_pulse"})

    def accept_response(self, received, now):
        payload, rssi, snr = received
        pending = self.pending
        try:
            kind, node, seq, op, value = decode(self.nodes[pending["node"]], payload)
            if (kind, node, seq, op) != (1, pending["node"], pending["seq"], pending["op"]):
                raise ValueError("Unexpected response")
            if op in (SET_LED, SET_VALVE) and value != pending["value"]:
                raise ValueError("Unexpected actuator state")
        except ValueError:
            LOG.warning("Ignored invalid or unexpected radio response")
            return
        recovered = node not in self.seen or now - self.seen[node] > OFFLINE_TIMEOUT
        self.seen[node] = now
        self.last_ack[node] = (seq, op, value)
        base = f"{ROOT}/node/{node}"
        status = self.status.setdefault(node, {"node": node})
        status.update(sequence=seq, rssi=rssi, snr=snr, confirmed_at=time.time())
        if op in (GET_LED, SET_LED):
            self.next_poll[(node, GET_LED)] = now + POLL_INTERVAL
            if recovered:
                # A LED response proves the link is back, not the valve state.
                self.next_poll[(node, GET_VALVE)] = now
                LOG.info("Node %d link recovered; valve query due immediately", node)
            status["led"] = bool(value)
            self.publish(base + "/led/state", "ON" if value else "OFF")
        else:
            self.next_poll[(node, GET_VALVE)] = now + POLL_INTERVAL
            self.valve_seen[node] = now
            state = {0: "closed", 1: "open", VALVE_UNKNOWN: "None"}[value]
            status["valve"] = "unknown" if value == VALVE_UNKNOWN else state
            self.publish(base + "/valve/state", state)
            self.publish(base + "/valve/status", {
                "sequence": seq, "confirmation": "unknown" if value == VALVE_UNKNOWN else "confirmed",
                "state_source": "gpio_pulse", "rssi": rssi, "snr": snr,
                "confirmed_at": status["confirmed_at"]})
            self.publish(base + "/valve/availability", "online")
        self.publish(base + "/status", status)
        self.publish(base + "/availability", "online")
        LOG.info("ACK node=%d sequence=%d op=%d value=%d RSSI=%.1f SNR=%.1f", node, seq, op, value, rssi, snr)
        self.pending = None

    def expire_nodes(self, now):
        for node, seen in list(self.seen.items()):
            if now - seen > OFFLINE_TIMEOUT:
                self.publish(f"{ROOT}/node/{node}/availability", "offline")
                del self.seen[node]
        for node, seen in list(self.valve_seen.items()):
            if now - seen > OFFLINE_TIMEOUT:
                self.publish(f"{ROOT}/node/{node}/valve/availability", "offline")
                self.publish(f"{ROOT}/node/{node}/valve/state", "None")
                del self.valve_seen[node]

    def request_failed(self, now):
        p = self.pending
        LOG.warning("No ACK from node=%d sequence=%d op=%d", p["node"], p["seq"], p["op"])
        if p["op"] == SET_VALVE:
            self.publish(f"{ROOT}/node/{p['node']}/valve/state", "None")
            self.publish(f"{ROOT}/node/{p['node']}/valve/status", {
                "sequence": p["seq"], "confirmation": "unconfirmed", "state_source": "gpio_pulse"})
            self.next_poll[(p["node"], GET_VALVE)] = now
        self.pending = None

    def run(self):
        while not self.stop.is_set():
            now = time.monotonic()
            received = self.radio.poll()
            if received and self.pending:
                self.accept_response(received, now)
            self.expire_nodes(now)
            if not self.pending and self.client.is_connected():
                request = self.next_request(now)
                if request:
                    self.start_request(*request, now=now)
            if self.pending and now >= self.pending["next"]:
                p = self.pending
                if p["tries"] == MAX_TRIES:
                    self.request_failed(now)
                else:
                    self.radio.send(p["frame"])
                    p["tries"] += 1
                    p["next"] = time.monotonic() + ACK_TIMEOUT
            self.stop.wait(0.02)

    def close(self):
        try:
            self.publish(ROOT + "/bridge/availability", "offline").wait_for_publish(timeout=2)
        finally:
            self.client.disconnect()
            self.client.loop_stop()
            self.radio.close()


def smoke_test(bridge):
    """Drive the same MQTT command path used by Home Assistant; save fresh ACKs."""
    result = {"passed": False, "steps": []}
    path = Path("/config/smoke-test.json")
    path.write_text(json.dumps(result))
    node = next(iter(bridge.nodes))
    deadline = time.monotonic() + 15
    while node not in bridge.seen and time.monotonic() < deadline:
        if bridge.stop.wait(0.1):
            return
    try:
        if node not in bridge.seen:
            raise TimeoutError("Initial radio GET did not receive an ACK")
        for expected in ("ON", "OFF"):
            before = bridge.seen[node]
            bridge.client.publish(f"{ROOT}/node/{node}/led/set", expected, qos=1, retain=False).wait_for_publish(timeout=2)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                # A newer ACK must confirm a SET, not a periodic GET.
                ack = bridge.last_ack.get(node)
                if bridge.seen.get(node, 0) > before and ack and ack[1:] == (1, int(expected == "ON")):
                    result["steps"].append(expected)
                    break
                if bridge.stop.wait(0.05):
                    return
            else:
                raise TimeoutError(f"MQTT {expected} did not receive a radio ACK")
        result["passed"] = True
        LOG.info("MQTT -> LoRa -> node LED -> ACK smoke test passed")
    except Exception as error:
        result["error"] = str(error)
        LOG.error("Smoke test failed: %s", error)
    path.write_text(json.dumps(result, indent=2))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("LoRa bridge 0.3.0: queries every %ds per status; offline after %ds",
             POLL_INTERVAL, OFFLINE_TIMEOUT)
    options = json.loads(Path("/data/options.json").read_text())
    bridge = Bridge(options, Radio(options["frequency"]))
    signal.signal(signal.SIGTERM, lambda *_: bridge.stop.set())
    signal.signal(signal.SIGINT, lambda *_: bridge.stop.set())
    if options.get("self_test"):
        threading.Thread(target=smoke_test, args=(bridge,), daemon=True).start()
    try:
        bridge.run()
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
