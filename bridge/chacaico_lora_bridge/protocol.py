"""Authenticated Chacaico v3, with v2 transport for staged node upgrades."""
from dataclasses import dataclass
import hmac
import math
import struct
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers import algorithms

REQUEST, RESPONSE, READY = range(3)
GET_STATE, SET_LED, SET_VALVE, GET_CONFIG, SET_CONFIG, END, COMMIT_CONFIG = range(7)
OK, INVALID, STORE_FAILED, CONFLICT, BUSY, TRIAL = range(6)
UNKNOWN = 2
MAX_SLEEP, MIN_PULSE, MAX_PULSE = 3600, 10, 200
LEGACY_BODY = struct.Struct("<2sBBHIIIBBIHHBB")
BODY = struct.Struct("<2sBBHIIIBBIHHBBBHHhbB")
FRAME_SIZE = BODY.size + 8
CONFIG_DEFAULTS = {"sleep_s": 0, "pulse_ms": 50, "tx_power_dbm": 0,
                   "listen_ms": 3000, "max_awake_ms": 10000}
CONFIG_KEYS = tuple(CONFIG_DEFAULTS)
POLICY_DEFAULTS = {"command_ttl_s": 0, "missed_contacts": 3}
CONFIG_LIMITS = {"sleep_s": (0, 3600), "pulse_ms": (10, 200),
                 "tx_power_dbm": (0, 22), "listen_ms": (1000, 10000),
                 "max_awake_ms": (5000, 60000)}
POLICY_LIMITS = {"command_ttl_s": (0, 7200), "missed_contacts": (1, 20)}

@dataclass(frozen=True)
class Frame:
    kind: int
    node: int
    boot: int
    wake: int
    sequence: int
    op: int = GET_STATE
    status: int = OK
    revision: int = 0
    sleep_s: int = 0
    pulse_ms: int = 0
    valve: int = 0
    led: int = 0
    tx_power_dbm: int = 0
    listen_ms: int = 3000
    max_awake_ms: int = 10000
    downlink_rssi: int = 32767
    downlink_snr: int = 127
    flags: int = 0
    version: int = 3

def max_pulse_ms(node):
    return 3000 if node in (1, 2) else MAX_PULSE

def valid_config(sleep_s, pulse_ms, node=None, tx_power_dbm=0, listen_ms=3000, max_awake_ms=10000):
    values = dict(sleep_s=sleep_s, pulse_ms=pulse_ms, tx_power_dbm=tx_power_dbm,
                  listen_ms=listen_ms, max_awake_ms=max_awake_ms)
    return (all(type(v) is int and CONFIG_LIMITS[k][0] <= v <=
                (max_pulse_ms(node) if k == "pulse_ms" else CONFIG_LIMITS[k][1])
                for k, v in values.items())
            and max_awake_ms >= max(listen_ms + 1000, pulse_ms + 2000))

def valid_policy(values):
    return set(values) == set(POLICY_DEFAULTS) and all(type(v) is int and
        POLICY_LIMITS[k][0] <= v <= POLICY_LIMITS[k][1] for k, v in values.items())

def airtime_seconds(length=FRAME_SIZE):
    # Current fixed PHY only: SF7, BW125, CR4/5, explicit header, CRC, preamble8.
    symbols = 8 + math.ceil((8 * length - 4 * 7 + 28 + 16) / (4 * 7)) * 5
    return (8 + 4.25 + symbols) * 2**7 / 125000

def tag(key, data):
    mac = CMAC(algorithms.AES(key)); mac.update(data)
    return mac.finalize()[:8]

def encode(key, frame):
    fields = (b"CL", frame.version, frame.kind, frame.node, frame.boot, frame.wake,
              frame.sequence, frame.op, frame.status, frame.revision,
              frame.sleep_s, frame.pulse_ms, frame.valve, frame.led)
    if frame.version == 2:
        if frame.op > END or frame.status > BUSY:
            raise ValueError("Unsupported legacy operation")
        body = LEGACY_BODY.pack(*fields)
    elif frame.version == 3:
        body = BODY.pack(*fields, frame.tx_power_dbm, frame.listen_ms, frame.max_awake_ms,
                         frame.downlink_rssi, frame.downlink_snr, frame.flags)
    else:
        raise ValueError("Unsupported protocol")
    return body + tag(key, body)

def decode(key, packet):
    version = packet[2] if len(packet) >= 3 else 0
    layout = {2: LEGACY_BODY, 3: BODY}.get(version)
    if not layout or len(packet) != layout.size + 8 or not hmac.compare_digest(tag(key, packet[:-8]), packet[-8:]):
        raise ValueError("Invalid length/authentication")
    magic, version, *fields = layout.unpack(packet[:-8])
    f = Frame(*fields, version=version)
    if (magic != b"CL" or f.kind not in (REQUEST, RESPONSE, READY)
            or not 1 <= f.node <= 65534 or f.op not in range(6 if version == 2 else 7)
            or f.status not in range(5 if version == 2 else 6) or f.valve not in (0, 1, UNKNOWN)
            or f.led not in (0, 1) or f.flags not in (0, 1)):
        raise ValueError("Invalid fields")
    if f.kind == READY and (f.op != GET_STATE or f.sequence != 0):
        raise ValueError("Invalid announcement")
    if f.kind == REQUEST:
        if f.status or not f.boot or not f.wake or not f.sequence or f.valve == UNKNOWN or f.flags:
            raise ValueError("Invalid request")
    elif (not valid_config(**{k: getattr(f, k) for k in CONFIG_KEYS}, node=f.node)
          or not f.revision or bool(f.flags) != (f.status == TRIAL)):
        raise ValueError("Invalid reported configuration")
    return f

def node_id(packet):
    if len(packet) not in (LEGACY_BODY.size + 8, FRAME_SIZE) or packet[:2] != b"CL" or packet[2] not in (2, 3):
        raise ValueError("Invalid frame")
    return int.from_bytes(packet[4:6], "little")
