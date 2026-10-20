"""Single-threaded radio scheduler. MQTT callbacks feed it through a queue."""
from dataclasses import dataclass, field, replace
import json
import logging
import math
import os
from pathlib import Path
from protocol import *

LOG = logging.getLogger("chacaico")
ROOT = "chacaico/lora"
ERRORS = {INVALID: "Parámetros inválidos", STORE_FAILED: "Error de memoria",
          CONFLICT: "Conflicto de revisión", BUSY: "Ventana terminando"}


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Sequence:
    """Reserve blocks before use; no SD write for each wake/packet."""
    def __init__(self, path):
        self.path = path
        self.value = json.loads(path.read_text()) if path.exists() else 0
        if type(self.value) is not int or not 0 <= self.value <= 0xffffffff:
            raise ValueError("Invalid sequence store; restore its backup")
        self.limit = self.value

    def next(self):
        if self.value == self.limit:
            if self.value > 0xffffffff - 1024:
                raise ValueError("Sequence space exhausted")
            atomic_json(self.path, self.value + 1024)
            self.limit = self.value + 1024
        self.value += 1
        return self.value


@dataclass
class Node:
    ident: int
    boot: int = 0
    wake: int = 0
    seen: float = -math.inf
    active_until: float = 0
    hard_until: float = 0
    next_query: float = 0
    advertised: dict = field(default_factory=lambda: {"revision": 1, "sleep_s": 0, "pulse_ms": 50})
    confirmed: dict | None = None
    draft: dict | None = None
    config_job: dict | None = None
    config_status: str = "Sin confirmar"
    config_error: str | None = None
    command_status: str = "Sin órdenes pendientes"
    verified: bool = False
    need_query: bool = True
    reconcile: bool = False
    closed: bool = False
    radio_fault: bool = False
    pending: dict | None = None
    actions: dict = field(default_factory=dict)
    action_status: dict = field(default_factory=dict)
    backoff: float = 0
    last_tx: float = -math.inf


class Engine:
    def __init__(self, keys, directory, publish, monotonic, wall):
        self.keys, self.publish, self.now, self.wall = keys, publish, monotonic, wall
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.file = directory / "runtime-v2.json"
        self.sequence = Sequence(directory / "sequence.json")
        saved = json.loads(self.file.read_text()) if self.file.exists() else {"version": 1, "nodes": {}}
        if saved.get("version") != 1 or not isinstance(saved.get("nodes"), dict):
            raise ValueError("Invalid runtime store")
        self.nodes = {ident: Node(ident) for ident in keys}
        self.published = {}
        self.tx_ready = 0
        for ident, n in self.nodes.items():
            old = saved["nodes"].get(str(ident), {})
            n.confirmed, n.draft, n.config_job = (old.get(k) for k in ("confirmed", "draft", "config_job"))
            n.boot = old.get("boot", 0)
            n.config_error = old.get("config_error")
            if n.config_error:
                n.config_status = n.config_error
            for cfg in (n.confirmed, n.draft):
                if cfg and not valid_config(cfg.get("sleep_s"), cfg.get("pulse_ms"), node=ident):
                    raise ValueError("Invalid stored configuration")
            if n.confirmed:
                n.advertised = dict(n.confirmed)
            if n.config_job:
                if (not valid_config(n.config_job.get("sleep_s"), n.config_job.get("pulse_ms"), node=ident)
                        or not isinstance(n.config_job.get("deadline"), (int, float))
                        or not math.isfinite(n.config_job["deadline"])
                        or (n.config_job.get("revision") is not None and
                            (type(n.config_job["revision"]) is not int or not 1 <= n.config_job["revision"] <= 0xffffffff))):
                    raise ValueError("Invalid pending configuration")
                n.config_status = "Pendiente de contacto"

    def persist(self):
        atomic_json(self.file, {"version": 1, "nodes": {str(i): {
            "confirmed": n.confirmed, "draft": n.draft, "config_job": n.config_job,
            "boot": n.boot, "config_error": n.config_error} for i, n in self.nodes.items()}})

    def emit(self, node, suffix, value, force=False):
        if suffix == "command/status":
            self.nodes[node].command_status = value
        topic = f"{ROOT}/node/{node}/{suffix}"
        serialized = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
        if force or self.published.get(topic) != serialized:
            self.publish(topic, value)
            self.published[topic] = serialized

    def action_view(self, n, op, status):
        # Last actuator command is independent from telemetry and the other actuator.
        n.action_status[op] = status
        resource = "valve" if op == SET_VALVE else "led"
        self.emit(n.ident, resource + "/command/status", status)
        self.emit(n.ident, "command/status", status)

    def config_view(self, n):
        draft = n.draft or n.confirmed or {"sleep_s": 0, "pulse_ms": 50}
        self.emit(n.ident, "config/draft", {k: draft[k] for k in ("sleep_s", "pulse_ms")})
        self.emit(n.ident, "config/status", n.config_status)
        if n.confirmed:
            self.emit(n.ident, "config/reported", n.confirmed)

    def reconnect(self):
        self.published.clear()
        for n in self.nodes.values():
            n.need_query = True
            self.config_view(n)
            for op, resource in ((SET_VALVE, "valve"), (SET_LED, "led")):
                self.emit(n.ident, resource + "/command/status",
                          n.action_status.get(op, "Sin órdenes pendientes"))
            self.emit(n.ident, "command/status", n.command_status)
        self.tick()

    def message(self, node, resource, payload, retained=False):
        if retained or node not in self.nodes:
            return
        n = self.nodes[node]
        if resource.startswith("config/") and resource.endswith("/set"):
            name = resource.split("/")[1]
            if name not in ("sleep_s", "pulse_ms"):
                return
            try:
                value = float(payload)
                if not math.isfinite(value) or not value.is_integer():
                    return
                draft = {k: (n.draft or n.confirmed or n.advertised)[k] for k in ("sleep_s", "pulse_ms")}
                draft[name] = int(value)
                if not valid_config(**draft, node=node):
                    return
            except (ValueError, OverflowError):
                return
            n.draft = draft
            self.persist()
            self.config_view(n)
            return
        if resource == "config/apply" and payload == "APPLY":
            n.config_error = None
            cfg = dict(n.draft or n.confirmed or n.advertised)
            cfg = {k: cfg[k] for k in ("sleep_s", "pulse_ms")}
            if n.verified and n.confirmed and all(n.confirmed[k] == cfg[k] for k in cfg) and not n.config_job:
                n.config_status = "Confirmada"
            elif n.config_job and all(n.config_job[k] == cfg[k] for k in cfg):
                return  # A repeated click is the same durable transaction.
            else:
                n.config_job = {**cfg, "revision": None, "deadline": self.wall() + 86400}
                n.config_status = "Pendiente de contacto"
                n.need_query = True
            self.persist()
            self.config_view(n)
            return
        if resource == "config/query" and payload == "QUERY":
            n.config_error = None
            self.persist()
            n.need_query = True
            n.config_status = "Consultando" if not n.config_job else "Pendiente de contacto"
            self.config_view(n)
            return
        choices = {"led/set": (SET_LED, {"ON": 1, "OFF": 0}), "valve/set": (SET_VALVE, {"OPEN": 1, "CLOSE": 0})}
        if resource not in choices or payload not in choices[resource][1]:
            return
        op, values = choices[resource]
        value = values[payload]
        prior = n.actions.get(op)
        if prior and prior["value"] == value:
            return
        sleep = max(n.advertised["sleep_s"], (n.config_job or {}).get("sleep_s", 0))
        # Latest intent replaces an unsent opposite command, including a queued OPEN.
        n.actions[op] = {"value": value, "deadline": self.now() + max(15, sleep + 20)}
        if n.pending and n.pending["frame"].op == op:
            n.pending = None  # Old ACK is no longer evidence for the current intent.
        self.emit(node, "valve/status" if op == SET_VALVE else "led/status",
                  {"confirmation": "pending", "command": payload, "state_source": "gpio_pulse" if op == SET_VALVE else "led"})
        self.action_view(n, op, "Pendiente")

    def receive(self, packet, rssi, snr):
        try:
            ident = node_id(packet)
            f = decode(self.keys[ident], packet)
        except (ValueError, KeyError):
            return
        n = self.nodes[ident]
        now = self.now()
        if f.kind == READY:
            if f.boot < n.boot or (f.boot == n.boot and f.wake < n.wake):
                return
            if not f.boot or not f.wake:
                self.emit(ident, "config/status", "Error de memoria")
                return
            new = (f.boot, f.wake) != (n.boot, n.wake)
            if new:
                new_boot = f.boot != n.boot
                n.boot, n.wake = f.boot, f.wake
                if n.pending and n.pending["frame"].op in (SET_LED, SET_VALVE, SET_CONFIG):
                    n.reconcile = True
                n.pending = None
                n.closed = False
                n.need_query = n.need_query or new_boot or not n.verified
                n.active_until = now + 2.8
                n.hard_until = now + 9.5
                n.backoff = now + .15
                if new_boot:
                    n.verified = False
                    self.emit(ident, "valve/state", "None")
                    self.persist()
            elif n.closed:
                return  # An old repeated READY never reopens a completed window.
            n.advertised = self.configuration(f)
            n.radio_fault = f.status != OK
            if n.radio_fault:
                n.config_status = ERRORS.get(f.status, "Error del nodo")
                self.config_view(n)
                return
            if not f.sleep_s:
                n.active_until = math.inf
            # READY is a hint, not confirmation of the requested configuration.
            return
        p = n.pending
        if f.kind != RESPONSE or not p:
            return
        expected = p["frame"]
        if (f.boot, f.wake, f.sequence, f.op) != (expected.boot, expected.wake, expected.sequence, expected.op):
            return
        if f.status == OK:
            if f.op == SET_LED and f.led != expected.led:
                return
            if f.op == SET_VALVE and f.valve != expected.valve:
                return
            if f.op == SET_CONFIG and self.configuration(f) != {
                    "revision": expected.revision, "sleep_s": expected.sleep_s, "pulse_ms": expected.pulse_ms}:
                return
        n.pending = None
        n.seen = now
        n.backoff = now + .15
        if f.sleep_s and not n.advertised["sleep_s"]:
            n.hard_until = now + 9
        if f.sleep_s:
            n.active_until = min(now + 2.8, n.hard_until)
        else:
            n.active_until = math.inf
            n.closed = False
        self.report(n, f, rssi, snr)
        if f.status != OK:
            if f.status == BUSY:
                n.closed = True
                return
            if f.op == SET_CONFIG and n.config_job:
                if f.status == CONFLICT:
                    n.config_job["revision"] = None
                    n.need_query = True
                else:
                    n.config_job = None
                    n.config_error = n.config_status = ERRORS[f.status]
                self.persist()
                self.config_view(n)
            return
        if f.op in (GET_STATE, GET_CONFIG):
            n.need_query = False
            n.reconcile = False
            n.next_query = now + 30
        if f.op in (SET_LED, SET_VALVE):
            job = n.actions.get(f.op)
            actual = f.led if f.op == SET_LED else f.valve
            if job and job["value"] == actual:
                del n.actions[f.op]
                self.action_view(n, f.op, "Confirmada")
        if f.op == END and f.sleep_s:
            n.closed = True
        LOG.info("ACK node=%d boot=%d wake=%d seq=%d op=%d result=%d revision=%d sleep=%d pulse=%d",
                 ident, f.boot, f.wake, f.sequence, f.op, f.status, f.revision, f.sleep_s, f.pulse_ms)

    @staticmethod
    def configuration(f):
        return {"revision": f.revision, "sleep_s": f.sleep_s, "pulse_ms": f.pulse_ms}

    def report(self, n, f, rssi, snr):
        cfg = self.configuration(f)
        changed = not n.confirmed or any(n.confirmed.get(k) != v for k, v in cfg.items())
        n.advertised = cfg
        n.confirmed = {**cfg, "confirmed_at": self.wall()}
        n.verified = True
        if n.draft is None:
            n.draft = {k: cfg[k] for k in ("sleep_s", "pulse_ms")}
            changed = True
        job = n.config_job
        if job and all(cfg[k] == job[k] for k in ("sleep_s", "pulse_ms")):
            # Includes recovery after a lost SET_CONFIG ACK or bridge restart.
            if job["revision"] is None or cfg["revision"] >= job["revision"]:
                n.config_job = None
                changed = True
        n.config_status = n.config_error or ("Confirmada" if not n.config_job else "Pendiente")
        if changed:
            self.persist()
        for op, actual in ((SET_LED, f.led), (SET_VALVE, f.valve)):
            job = n.actions.get(op)
            if job and job["value"] == actual:
                del n.actions[op]
                self.action_view(n, op, "Confirmada")
        self.config_view(n)
        self.emit(n.ident, "led/state", "ON" if f.led else "OFF")
        self.emit(n.ident, "valve/state", {0: "closed", 1: "open", UNKNOWN: "None"}[f.valve])
        self.emit(n.ident, "valve/status", {"sequence": f.sequence, "confirmation": "unknown" if f.valve == UNKNOWN else "confirmed",
                  "state_source": "gpio_pulse", "confirmed_at": self.wall(), "rssi": rssi, "snr": snr})
        self.emit(n.ident, "status", {"node": n.ident, "sequence": f.sequence, "boot": f.boot, "wake": f.wake,
                  "rssi": rssi, "snr": snr, "confirmed_at": self.wall(), "led": bool(f.led),
                  "valve": {0: "closed", 1: "open", UNKNOWN: "unknown"}[f.valve], "firmware": "0.4.1" if n.ident in (1, 2) else "0.4.0"})

    def tick(self):
        now = self.now()
        for n in self.nodes.values():
            alive = now - n.seen < max(90, 3 * (n.advertised["sleep_s"] + 10) + 10)
            self.emit(n.ident, "availability", "online" if alive else "offline")
            self.emit(n.ident, "valve/availability", "online" if alive and n.verified else "offline")
            state = "Sin contacto" if not alive else (
                "Reposo esperado" if n.advertised["sleep_s"] and (n.closed or now >= n.active_until)
                else "Escuchando")
            self.emit(n.ident, "link/state", state)
            for op, job in list(n.actions.items()):
                if now > job["deadline"]:
                    del n.actions[op]
                    if n.pending and n.pending["frame"].op == op:
                        n.pending = None
                    self.action_view(n, op, "Vencida sin confirmar")
                    self.emit(n.ident, "valve/status" if op == SET_VALVE else "led/status",
                              {"confirmation": "unconfirmed", "expired": True})
                    n.need_query = True
            if n.config_job and self.wall() > n.config_job["deadline"]:
                n.config_job = None
                if n.pending and n.pending["frame"].op == SET_CONFIG:
                    n.pending = None
                n.config_error = n.config_status = "Vencida sin confirmar"
                self.persist()
                self.config_view(n)
            p = n.pending
            if p and now >= p["next"] and p["tries"] >= 3:
                n.pending = None
                if p["frame"].op == END:
                    n.closed = bool(n.advertised["sleep_s"])
                else:
                    n.need_query = True
                    n.reconcile = True
                    n.backoff = now + 1
                    if p["frame"].op in (SET_VALVE, SET_LED):
                        self.action_view(n, p["frame"].op, "Sin confirmación; consultando")
                    else:
                        self.emit(n.ident, "command/status", "Sin confirmación; consultando")
                    if p["frame"].op == SET_CONFIG:
                        n.config_status = "Sin confirmación; consultando"
                        self.config_view(n)
            if n.pending and now >= n.active_until:
                if n.pending["frame"].op in (SET_LED, SET_VALVE, SET_CONFIG):
                    n.reconcile = True
                n.pending = None
                n.need_query = True

    def start(self, n, op, **values):
        f = Frame(REQUEST, n.ident, n.boot, n.wake, self.sequence.next(), op, **values)
        n.pending = {"frame": f, "packet": encode(self.keys[n.ident], f), "tries": 0, "next": 0}

    def next_frame(self):
        self.tick()
        now = self.now()
        if now < self.tx_ready:
            return None
        candidates = [n for n in self.nodes.values() if n.boot and n.wake and not n.closed and not n.radio_fault
                      and now < n.active_until and now >= n.backoff]
        # Round-robin by last transmission; offline nodes never occupy another window.
        for n in sorted(candidates, key=lambda item: (item.active_until, item.last_tx)):
            if n.pending:
                if now < n.pending["next"]:
                    continue
            else:
                required = 1.2 + (n.advertised["pulse_ms"] / 1000 if SET_VALVE in n.actions else 0)
                if n.advertised["sleep_s"] and n.hard_until - now < required:
                    self.start(n, END)
                elif SET_VALVE in n.actions and n.actions[SET_VALVE]["value"] == 0:
                    self.start(n, SET_VALVE, valve=0)
                elif n.reconcile:
                    self.start(n, GET_CONFIG)
                elif n.actions:
                    # A session-bound actuator ACK also reports the full state/config.
                    # Deliver the user's intent before background queries can consume
                    # a short window. Lost-ACK retries remain the same transaction.
                    op = SET_VALVE if SET_VALVE in n.actions else SET_LED
                    self.start(n, op, **{"valve" if op == SET_VALVE else "led": n.actions[op]["value"]})
                elif n.need_query or (not n.advertised["sleep_s"] and now >= n.next_query):
                    self.start(n, GET_CONFIG)
                elif n.config_job:
                    job = n.config_job
                    if job["revision"] is None:
                        job["revision"] = n.advertised["revision"] + 1
                        if job["revision"] > 0xffffffff:
                            n.config_status = "Revisión agotada";n.config_job = None
                            self.persist();self.config_view(n);continue
                        self.persist()
                    self.start(n, SET_CONFIG, revision=job["revision"], sleep_s=job["sleep_s"], pulse_ms=job["pulse_ms"])
                elif n.advertised["sleep_s"]:
                    self.start(n, END)
                else:
                    continue
            n.last_tx = now
            return n.ident, n.pending["packet"]
        return None

    def sent(self, node, success=True):
        n = self.nodes[node]
        p = n.pending
        if not p:
            return
        now = self.now()
        p["tries"] += 1
        valve_pulse = n.advertised["pulse_ms"] / 1000 if p["frame"].op == SET_VALVE else 0
        p["next"] = now + 1.5 + valve_pulse
        # The ACK follows the completed GPIO pulse. Reserve RX through its airtime.
        self.tx_ready = now + (max(.65, valve_pulse + .4) if p["frame"].op == SET_VALVE else .4)
        if n.advertised["sleep_s"] and p["frame"].op != END:
            n.active_until = min(now + valve_pulse + 2.8, n.hard_until)
        if not success:
            n.need_query = True
        if p["frame"].op == END:
            p["tries"] = 3  # Missing END ACK is harmless; do not transmit into its sleep.
