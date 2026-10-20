"""Chacaico v2: authenticated boot/window-bound transactions (38 bytes)."""
from dataclasses import dataclass
import hmac
import struct
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers import algorithms

REQUEST, RESPONSE, READY = range(3)
GET_STATE, SET_LED, SET_VALVE, GET_CONFIG, SET_CONFIG, END = range(6)
OK, INVALID, STORE_FAILED, CONFLICT, BUSY = range(5)
UNKNOWN = 2
MAX_SLEEP, MIN_PULSE, MAX_PULSE = 3600, 10, 200
BODY = struct.Struct("<2sBBHIIIBBIHHBB")
FRAME_SIZE = BODY.size + 8


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


def max_pulse_ms(node):
    # Commissioning exception explicitly requested for the isolated node 1.
    return 3000 if node == 1 else MAX_PULSE


def valid_config(sleep_s, pulse_ms, node=None):
    return (type(sleep_s) is int and type(pulse_ms) is int
            and 0 <= sleep_s <= MAX_SLEEP and MIN_PULSE <= pulse_ms <= max_pulse_ms(node))


def tag(key, data):
    mac = CMAC(algorithms.AES(key))
    mac.update(data)
    return mac.finalize()[:8]


def encode(key, frame):
    body = BODY.pack(b"CL", 2, frame.kind, frame.node, frame.boot, frame.wake,
                     frame.sequence, frame.op, frame.status, frame.revision,
                     frame.sleep_s, frame.pulse_ms, frame.valve, frame.led)
    return body + tag(key, body)


def decode(key, packet):
    if len(packet) != FRAME_SIZE or not hmac.compare_digest(tag(key, packet[:-8]), packet[-8:]):
        raise ValueError("Invalid length/authentication")
    magic, version, *fields = BODY.unpack(packet[:-8])
    f = Frame(*fields)
    if (magic != b"CL" or version != 2 or f.kind not in (REQUEST, RESPONSE, READY)
            or not 1 <= f.node <= 65534 or f.op not in range(6)
            or f.status not in range(5) or f.valve not in (0, 1, UNKNOWN) or f.led not in (0, 1)):
        raise ValueError("Invalid fields")
    if f.kind == READY and (f.op != GET_STATE or f.sequence != 0):
        raise ValueError("Invalid announcement")
    if f.kind == REQUEST:
        if f.status or not f.boot or not f.wake or not f.sequence or f.valve == UNKNOWN:
            raise ValueError("Invalid request")
    elif not valid_config(f.sleep_s, f.pulse_ms, node=f.node) or not f.revision:
        raise ValueError("Invalid reported configuration")
    return f


def node_id(packet):
    if len(packet) != FRAME_SIZE or packet[:3] != b"CL\x02":
        raise ValueError("Invalid frame")
    return int.from_bytes(packet[4:6], "little")
