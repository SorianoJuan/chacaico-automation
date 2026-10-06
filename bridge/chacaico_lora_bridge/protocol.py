"""Bench protocol: addressed LED/valve commands with an AES-CMAC-64 tag."""
import hmac
import struct

from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers import algorithms

HEADER = struct.Struct("<2sBBHIBB")
GET_LED, SET_LED, SET_VALVE, GET_VALVE = range(4)
VALVE_UNKNOWN = 2


def tag(key, data):
    mac = CMAC(algorithms.AES(key))
    mac.update(data)
    return mac.finalize()[:8]


def encode(key, kind, node, sequence, operation, value):
    header = HEADER.pack(b"CL", 1, kind, node, sequence, operation, value)
    return header + tag(key, header)


def decode(key, packet):
    if len(packet) != 20 or not hmac.compare_digest(tag(key, packet[:12]), packet[12:]):
        raise ValueError("Invalid length or authentication tag")
    magic, version, kind, node, sequence, operation, value = HEADER.unpack(packet[:12])
    allowed_value = value in (0, 1) or (kind == 1 and operation == GET_VALVE and value == VALVE_UNKNOWN)
    if (magic != b"CL" or version != 1 or kind not in (0, 1)
            or operation not in (GET_LED, SET_LED, SET_VALVE, GET_VALVE) or not allowed_value
            or (kind == 0 and operation in (GET_LED, GET_VALVE) and value != 0)):
        raise ValueError("Invalid protocol fields")
    return kind, node, sequence, operation, value
