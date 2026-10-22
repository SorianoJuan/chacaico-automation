#!/usr/bin/env python3
"""MQTT discovery/transport for the Chacaico v3 scheduler."""
import json
import logging
import os
from pathlib import Path
import queue
import signal
import threading
import time
import urllib.request
import paho.mqtt.client as mqtt
from engine import Engine, ROOT
from protocol import max_pulse_ms, CONFIG_LIMITS, POLICY_LIMITS
from radio import Radio

LOG = logging.getLogger("chacaico")


def mqtt_service():
    request = urllib.request.Request("http://supervisor/services/mqtt",
        headers={"Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]})
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    if result.get("result") != "ok":
        raise RuntimeError("MQTT service unavailable")
    return result["data"]


def discovery(node):
    base = f"{ROOT}/node/{node}"
    device = {"identifiers": [f"chacaico_cubecell_{node}"], "name": f"CubeCell {node}",
              "manufacturer": "Heltec", "model": "HTCC-AB01"}
    online = [{"topic": ROOT + "/bridge/availability"}]
    common = {"device": device, "availability_mode": "all", "availability": online, "qos": 1}
    def item(component, key, name, **settings):
        return (f"homeassistant/{component}/chacaico_node_{node}/{key}/config",
                {**common, "name": name, "unique_id": f"chacaico_node_{node}_{key}", **settings})
    yield item("switch", "led", "LED de prueba", state_topic=base + "/led/state",
               command_topic=base + "/led/set", payload_on="ON", payload_off="OFF", retain=False,
               availability=online + [{"topic": base + "/availability"}],
               icon="mdi:led-on", json_attributes_topic=base + "/status")
    yield item("valve", "valve", "Electroválvula", default_entity_id=f"valve.chacaico_node_{node}",
               state_topic=base + "/valve/state", command_topic=base + "/valve/set",
               payload_open="OPEN", payload_close="CLOSE", optimistic=False, retain=False,
               availability=online + [{"topic": base + "/valve/availability"}],
               icon="mdi:valve", json_attributes_topic=base + "/valve/status")
    yield item("sensor", "valve_command_status", "Orden de válvula",
               default_entity_id=f"sensor.chacaico_node_{node}_valve_command_status",
               state_topic=base + "/valve/command/status", icon="mdi:list-status")
    for key, unit, name in (("rssi", "dBm", "RSSI"), ("snr", "dB", "SNR")):
        yield item("sensor", key, name, state_topic=base + "/status",
                   value_template="{{ value_json." + key + " }}", unit_of_measurement=unit,
                   state_class="measurement", entity_category="diagnostic",
                   availability=online + [{"topic": base + "/availability"}])
    for key, name, unit, minimum, maximum in (
            ("sleep_s", "Reposo solicitado", "s", 0, 3600),
            ("pulse_ms", "Pulso solicitado", "ms", 10, max_pulse_ms(node)),
            ("tx_power_dbm", "Potencia TX solicitada", "dBm", 0, 22),
            ("listen_ms", "Escucha solicitada", "ms", 1000, 10000),
            ("max_awake_ms", "Máximo despierto solicitado", "ms", 5000, 60000)):
        yield item("number", key + "_requested", name,
                   default_entity_id=f"number.chacaico_node_{node}_{key}_requested",
                   state_topic=base + "/config/draft", value_template="{{ value_json." + key + " }}",
                   command_topic=base + f"/config/{key}/set", optimistic=False, retain=False,
                   mode="box", min=minimum, max=maximum, step=1, unit_of_measurement=unit,
                   entity_category="config")
        yield item("sensor", key + "_confirmed", name.replace("solicitado", "confirmado").replace("solicitada", "confirmada"),
                   default_entity_id=f"sensor.chacaico_node_{node}_{key}_confirmed",
                   state_topic=base + "/config/reported", value_template="{{ value_json." + key + " }}",
                   unit_of_measurement=unit, entity_category="diagnostic")
    for key, label, unit in (("command_ttl_s", "Vigencia de órdenes", "s"),
                              ("missed_contacts", "Contactos perdidos tolerados", None)):
        minimum, maximum = POLICY_LIMITS[key]
        yield item("number", key + "_requested", label + " solicitada",
                   default_entity_id=f"number.chacaico_node_{node}_{key}_requested",
                   state_topic=base + "/policy/draft", value_template="{{ value_json." + key + " }}",
                   command_topic=base + f"/policy/{key}/set", optimistic=False, retain=False,
                   mode="box", min=minimum, max=maximum, step=1, entity_category="config",
                   **({"unit_of_measurement": unit} if unit else {}))
        yield item("sensor", key + "_confirmed", label + " aplicada",
                   default_entity_id=f"sensor.chacaico_node_{node}_{key}_confirmed",
                   state_topic=base + "/policy/reported", value_template="{{ value_json." + key + " }}",
                   entity_category="diagnostic", **({"unit_of_measurement": unit} if unit else {}))
    yield item("button", "policy_apply", "Aplicar política del puente",
               default_entity_id=f"button.chacaico_node_{node}_policy_apply",
               command_topic=base + "/policy/apply", payload_press="APPLY", retain=False, entity_category="config")
    for key, label, unit in (
        ("uplink_rssi", "RSSI recibido por HAT", "dBm"), ("uplink_snr", "SNR recibido por HAT", "dB"),
        ("downlink_rssi", "RSSI recibido por nodo", "dBm"), ("downlink_snr", "SNR recibido por nodo", "dB"),
        ("orders", "Órdenes aceptadas", None), ("confirmed", "Órdenes confirmadas", None),
        ("expired", "Órdenes vencidas", None), ("superseded", "Órdenes sustituidas", None),
        ("pending", "Órdenes pendientes", None), ("success_percent", "Éxito de órdenes finalizadas", "%"),
        ("tx_attempts", "Intentos de transmisión", None), ("tx_errors", "Errores de transmisión", None),
        ("retries", "Reenvíos de transacción", None), ("acks", "Respuestas válidas", None),
        ("last_attempts", "Envíos de última orden", None), ("last_queue_s", "Espera antes del primer envío", "s"),
        ("last_delivery_s", "Demora desde primer envío", "s"), ("last_total_s", "Demora total de última orden", "s"),
        ("last_ack_ms", "Tiempo de última respuesta", "ms"),
        ("command_ttl_s", "Vigencia efectiva de nuevas órdenes", "s"),
        ("contact_timeout_s", "Plazo sin contacto", "s")):
        yield item("sensor", "metric_" + key, label,
                   default_entity_id=f"sensor.chacaico_node_{node}_metric_{key}",
                   state_topic=base + "/metrics", value_template="{{ value_json." + key + " }}",
                   entity_category="diagnostic", **({"unit_of_measurement": unit} if unit else {}))
    yield item("sensor", "metrics_started_at", "Inicio de métricas",
               default_entity_id=f"sensor.chacaico_node_{node}_metrics_started_at", state_topic=base + "/metrics",
               value_template="{{ value_json.started_at | timestamp_utc }}", device_class="timestamp", entity_category="diagnostic")
    for key, label, payload in (("apply", "Aplicar configuración", "APPLY"), ("query", "Consultar configuración", "QUERY")):
        yield item("button", "config_" + key, label,
                   default_entity_id=f"button.chacaico_node_{node}_config_{key}",
                   command_topic=base + "/config/" + key, payload_press=payload,
                   retain=False, entity_category="config")
    for key, label, suffix in (
            ("config_status", "Configuración", "config/status"),
            ("protocol", "Protocolo del nodo", "config/protocol"),
            ("config_input_error", "Validación de parámetros", "config/input_error"),
            ("policy_status", "Política del puente", "policy/status"),
            ("link", "Comunicación", "link/state"),
            ("command_status", "Última orden", "command/status")):
        yield item("sensor", key, label, default_entity_id=f"sensor.chacaico_node_{node}_{key}",
                   state_topic=base + "/" + suffix, entity_category="diagnostic")
    yield item("sensor", "config_revision", "Revisión confirmada",
               default_entity_id=f"sensor.chacaico_node_{node}_config_revision",
               state_topic=base + "/config/reported", value_template="{{ value_json.revision }}",
               json_attributes_topic=base + "/config/reported", entity_category="diagnostic")
    yield item("sensor", "config_confirmed_at", "Última confirmación",
               default_entity_id=f"sensor.chacaico_node_{node}_config_confirmed_at",
               state_topic=base + "/config/reported",
               value_template="{{ value_json.confirmed_at | timestamp_utc }}",
               device_class="timestamp", entity_category="diagnostic")



def bridge_discovery():
    base = ROOT + "/bridge"
    common = {"device": {"identifiers": ["chacaico_lora_bridge"], "name": "Chacaico HAT",
               "manufacturer": "Waveshare", "model": "SX1262 SKU24654"},
              "availability_topic": base + "/availability", "qos": 1}
    for component, key, label, settings in (
        ("number", "tx_power_requested", "Potencia TX solicitada", {
            "command_topic": base + "/power/set", "state_topic": base + "/power",
            "value_template": "{{ value_json.requested }}", "min": 0, "max": 22,
            "step": 1, "mode": "box", "unit_of_measurement": "dBm", "retain": False}),
        ("button", "power_apply", "Aplicar potencia HAT", {"command_topic": base + "/power/apply",
            "payload_press": "APPLY", "retain": False}),
        ("sensor", "tx_power_applied", "Potencia TX aplicada", {"state_topic": base + "/power",
            "value_template": "{{ value_json.applied }}", "unit_of_measurement": "dBm"}),
        ("sensor", "power_status", "Estado de potencia", {"state_topic": base + "/power",
            "value_template": "{{ value_json.status }}"})):
        yield (f"homeassistant/{component}/chacaico_bridge/{key}/config", {**common,
            "name": label, "unique_id": "chacaico_bridge_" + key,
            "default_entity_id": f"{component}.chacaico_bridge_{key}",
            "entity_category": "diagnostic" if component == "sensor" else "config", **settings})

class Bridge:
    def __init__(self, options, radio):
        self.radio, self.stop = radio, threading.Event()
        self.inbox = queue.Queue(maxsize=256)
        keys = {n["id"]: bytes.fromhex(n["key"]) for n in options["nodes"]}
        if not keys or len(keys) != len(options["nodes"]) or any(len(key) != 16 for key in keys.values()):
            raise ValueError("Invalid/duplicate node keys")
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="chacaico-lora-bridge")
        self.client.will_set(ROOT + "/bridge/availability", "offline", qos=1, retain=True)
        self.engine = Engine(keys, "/config", self.publish, time.monotonic, time.time, radio.set_power)
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

    def enqueue(self, message):
        try:
            self.inbox.put_nowait(message)
        except queue.Full:
            LOG.error("MQTT inbox full; discarded input")

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            LOG.error("MQTT connection rejected: %s", reason)
            return
        for topic, payload in bridge_discovery():
            self.publish(topic, payload)
        client.subscribe(ROOT + "/bridge/power/set", qos=1)
        client.subscribe(ROOT + "/bridge/power/apply", qos=1)
        for node in self.engine.nodes:
            for topic, payload in discovery(node):
                self.publish(topic, payload)
            client.subscribe(f"{ROOT}/node/{node}/+/set", qos=1)
            client.subscribe(f"{ROOT}/node/{node}/config/+/set", qos=1)
            client.subscribe(f"{ROOT}/node/{node}/config/apply", qos=1)
            client.subscribe(f"{ROOT}/node/{node}/config/query", qos=1)
            client.subscribe(f"{ROOT}/node/{node}/policy/+/set", qos=1)
            client.subscribe(f"{ROOT}/node/{node}/policy/apply", qos=1)
        self.enqueue(None)
        self.publish(ROOT + "/bridge/availability", "online")
        LOG.info("MQTT discovery published for %s", sorted(self.engine.nodes))

    def on_message(self, client, userdata, message):
        if message.retain or len(message.payload) > 128:
            return
        try:
            if message.topic.startswith(ROOT + "/bridge/"):
                self.enqueue((0, message.topic[len(ROOT + "/bridge/"):], message.payload.decode("ascii")))
                return
            prefix = ROOT + "/node/"
            if not message.topic.startswith(prefix):
                return
            node, resource = message.topic[len(prefix):].split("/", 1)
            self.enqueue((int(node), resource, message.payload.decode("ascii")))
        except (ValueError, UnicodeError):
            LOG.warning("Invalid MQTT input")

    def run(self):
        while not self.stop.is_set():
            received = self.radio.poll()
            if received:
                self.engine.receive(*received)
            for _ in range(8):
                try:
                    message = self.inbox.get_nowait()
                except queue.Empty:
                    break
                if message is None:
                    self.engine.reconnect()
                elif message[0] == 0:
                    self.engine.bridge_message(*message[1:])
                else:
                    self.engine.message(*message)
            self.engine.tick()
            if self.client.is_connected():
                outgoing = self.engine.next_frame()
                if outgoing:
                    node, payload = outgoing
                    try:
                        self.radio.send(payload)
                    except TimeoutError:
                        LOG.exception("Radio TX timeout node=%d", node)
                        self.engine.sent(node, False)
                    else:
                        self.engine.sent(node)
            self.stop.wait(.01)

    def close(self):
        try:
            self.publish(ROOT + "/bridge/availability", "offline").wait_for_publish(timeout=2)
        finally:
            self.client.disconnect()
            self.client.loop_stop()
            self.radio.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("Chacaico bridge 0.5.0; authenticated configuration and wake windows")
    options = json.loads(Path("/data/options.json").read_text())
    if options.get("self_test"):
        LOG.warning("Legacy self_test ignored: explicit tests only")
    bridge = Bridge(options, Radio(options["frequency"]))
    signal.signal(signal.SIGTERM, lambda *_: bridge.stop.set())
    signal.signal(signal.SIGINT, lambda *_: bridge.stop.set())
    try:
        bridge.run()
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
