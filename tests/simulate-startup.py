#!/usr/bin/env python3
"""Characterize bridge0.3.0 offline: real Bridge.run, modeled radio/node/MQTT.

No network, credentials, hardware, or Home Assistant frontend are used.
Assertions describe current behavior, including defects; revisit after fixing it.
"""
import argparse
import hashlib
import heapq
import importlib.util
import json
import logging
from pathlib import Path
import queue
import sys
import tempfile
import types
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
APP = ROOT_DIR / 'bridge/chacaico_lora_bridge'
sys.path.insert(0, str(APP))
if importlib.util.find_spec('paho') is None:
    for name in ('paho', 'paho.mqtt', 'paho.mqtt.client'):
        sys.modules[name] = types.ModuleType(name)
# Import the controller without importing hardware packages or constructing MQTT.
sys.modules['radio'] = types.SimpleNamespace(Radio=object)
import bridge as module
from protocol import encode, decode, GET_LED, SET_LED, SET_VALVE, GET_VALVE, VALVE_UNKNOWN

# Calculated SF7/BW125/CR4/5, explicit header, CRC, preamble8, payload20.
AIRTIME = 0.056576
TEST_KEYS = {1: bytes(range(16)), 2: bytes(range(16, 32))}


class Clock:
    def __init__(self):
        self.now = 0.0
        self.events = []
        self.ordinal = 0

    def at(self, at, callback):
        self.ordinal += 1
        heapq.heappush(self.events, (at, self.ordinal, callback))

    def advance(self, seconds):
        target = self.now + seconds
        while self.events and self.events[0][0] <= target:
            at, _, callback = heapq.heappop(self.events)
            self.now = at
            callback()
        self.now = target


class Stop:
    def __init__(self, clock, until):
        self.clock, self.until = clock, until

    def is_set(self):
        return self.clock.now >= self.until

    def wait(self, seconds):
        self.clock.advance(seconds)
        return self.is_set()


class Node:
    """Application-level counterpart, NOT the MCU/SX1262 driver or PCB."""
    def __init__(self, node_id, power_on=0, valve=VALVE_UNKNOWN):
        self.id, self.power_on = node_id, power_on
        self.valve, self.led = valve, False
        self.sequence = None
        self.request = self.cached_ack = None
        self.rx_ready = power_on
        self.pulses = []
        self.led_changes = []

    def receive(self, frame, now):
        if now < self.power_on or now < self.rx_ready:
            return None
        kind, node, seq, op, value = decode(TEST_KEYS[self.id], frame)
        if kind != 0 or node != self.id:
            return None
        if self.sequence is not None:
            signed_delta = ((seq - self.sequence + (1 << 31)) % (1 << 32)) - (1 << 31)
            if signed_delta < 0:
                return None
            if seq == self.sequence:
                return (0.025, self.cached_ack) if frame == self.request else None
        self.sequence, self.request = seq, frame
        delay = 0.025
        if op == SET_LED:
            self.led = bool(value)
            self.led_changes.append({'at': round(now, 6), 'value': value, 'sequence': seq})
        elif op == SET_VALVE:
            delay += 0.050
            self.valve = value
            self.pulses.append({'at': round(now, 6), 'value': value, 'sequence': seq})
        result = int(self.led) if op in (GET_LED, SET_LED) else self.valve
        self.cached_ack = encode(TEST_KEYS[self.id], 1, self.id, seq, op, result)
        return delay, self.cached_ack


class Link:
    def __init__(self, clock, nodes, turnaround, lose_request, lose_ack):
        self.clock, self.nodes = clock, nodes
        self.turnaround, self.lose_request, self.lose_ack = turnaround, lose_request, lose_ack
        self.inbox, self.trace = [], []
        self.receiving_since = 0
        self.transmission = 0

    def send(self, frame):
        node = int.from_bytes(frame[4:6], 'little')
        _, _, seq, op, value = decode(TEST_KEYS[node], frame)
        self.transmission += 1
        tx = {'at': round(self.clock.now, 6), 'node': node, 'sequence': seq, 'op': op, 'value': value}
        self.trace.append({'event': 'request', **tx})
        # The base cannot receive during request TX or the modeled TX->RX gap.
        self.receiving_since = self.clock.now + AIRTIME + self.turnaround(op, seq)
        request_end = self.clock.now + AIRTIME

        def deliver_request():
            if self.lose_request(tx) or node not in self.nodes:
                return
            reply = self.nodes[node].receive(frame, self.clock.now)
            if reply is None:
                return
            delay, packet = reply
            starts, ends = request_end + delay, request_end + delay + AIRTIME
            self.nodes[node].rx_ready = ends
            # Require RX by preamble start. Cases use a 200ms gap, longer than
            # the WHOLE ACK, so they do not rely on modeling late preamble capture.
            def deliver_ack():
                missed = self.receiving_since > starts or self.lose_ack(tx)
                self.trace.append({'event': 'ack_lost' if missed else 'ack_received',
                                   'at': round(self.clock.now, 6), 'node': node,
                                   'sequence': seq, 'op': op, 'value': packet[11]})
                if not missed:
                    self.inbox.append((packet, -55, 9))
            self.clock.at(ends, deliver_ack)

        self.clock.at(request_end, deliver_request)
        self.clock.advance(AIRTIME + self.turnaround(op, seq))

    def poll(self):
        return self.inbox.pop(0) if self.inbox else None


class Simulation:
    def __init__(self, nodes, until, configured=(1,), turnaround=lambda op, seq: 0.003,
                 lose_request=lambda tx: False, lose_ack=lambda tx: False):
        self.scratch = tempfile.TemporaryDirectory(prefix='chacaico-startup-sim-')
        self.clock = Clock()
        self.nodes = nodes
        self.publications = []
        b = self.bridge = module.Bridge.__new__(module.Bridge)
        b.nodes = {n: TEST_KEYS[n] for n in configured}
        b.commands = queue.Queue(32)
        b.seen, b.valve_seen, b.status, b.last_ack = {}, {}, {}, {}
        b.next_poll = {(n, op): 0 for n in configured for op in (GET_VALVE, GET_LED)}
        b.last_was_poll, b.pending, b.sequence = False, None, 0
        b.counter_file = Path(self.scratch.name) / 'sequence.json'
        b.client = types.SimpleNamespace(is_connected=lambda: True, subscribe=lambda *a, **kw: None)
        b.stop = Stop(self.clock, until)
        b.radio = Link(self.clock, nodes, turnaround, lose_request, lose_ack)
        b.publish = self.publish
        # Previous retained OFF is an explicit fixture, like a prior HA session.
        for n in configured:
            self.publish(f'{module.ROOT}/node/{n}/led/state', 'OFF')

    def publish(self, topic, value):
        self.publications.append({'at': round(self.clock.now, 6), 'topic': topic, 'payload': value})

    def command(self, at, node, actuator, payload):
        def issue():
            self.bridge.on_message(None, None, types.SimpleNamespace(
                topic=f'{module.ROOT}/node/{node}/{actuator}/set', payload=payload.encode(), retain=False))
        self.clock.at(at, issue)

    def run(self):
        virtual_time = types.SimpleNamespace(monotonic=lambda: self.clock.now,
                                            time=lambda: 1791300000 + self.clock.now)
        try:
            with patch.object(module, 'time', virtual_time):
                self.bridge.on_connect(self.bridge.client, None, None,
                                       types.SimpleNamespace(is_failure=False), None)
                self.bridge.run()
        finally:
            self.scratch.cleanup()
        return self

    def publications_for(self, node, topic, value=None):
        full = f'{module.ROOT}/node/{node}/{topic}'
        return [p for p in self.publications if p['topic'] == full
                and (value is None or p['payload'] == value)]

    def summary(self):
        return {'publications': [p for p in self.publications if not p['topic'].endswith('/config')],
                'radio': self.bridge.radio.trace,
                'nodes': {str(n): {'power_on': node.power_on, 'led': node.led,
                                  'valve': node.valve, 'pulses': node.pulses,
                                  'led_changes': node.led_changes}
                          for n, node in self.nodes.items()}}


def characterize():
    cases = {}
    # Both initial polls miss a node powered on after the first scan.
    s = Simulation({1: Node(1, power_on=15)}, until=70, configured=(1, 2)).run()
    online = s.publications_for(1, 'availability', 'online')[0]['at']
    assert online - 15 > 40
    cases['late_power_on'] = {'first_online_at': online, 'power_on_at': 15,
                             'discovery_delay_seconds': round(online - 15, 6), **s.summary()}

    # UI can use the LED while a missing peer monopolizes one retry transaction.
    s = Simulation({1: Node(1)}, until=8, configured=(1, 2))
    s.command(0.3, 1, 'led', 'ON')
    s.run()
    led_on = s.publications_for(1, 'led/state', 'ON')[0]['at']
    assert led_on - 0.3 > 2
    cases['offline_peer_delay'] = {'click_at': 0.3, 'led_confirmed_at': led_on,
                                  'delay_seconds': round(led_on - 0.3, 6), **s.summary()}

    # Three commands never reach the node; a later click works with the same loop.
    s = Simulation({1: Node(1)}, until=8,
                   lose_request=lambda tx: tx['op'] == SET_LED and tx['at'] < 4)
    s.command(1, 1, 'led', 'ON')
    s.command(5, 1, 'led', 'ON')
    s.run()
    assert len(s.nodes[1].led_changes) == 1 and s.nodes[1].led_changes[0]['at'] > 5
    cases['lost_first_led_request'] = s.summary()

    # Request executes but all SET ACKs are lost because RX starts after ACK end.
    lag = lambda op, seq: 0.2 if op in (SET_LED, SET_VALVE) else 0.003
    s = Simulation({1: Node(1)}, until=65, turnaround=lag)
    s.command(1, 1, 'led', 'ON')
    s.run()
    physical_at = s.nodes[1].led_changes[0]['at']
    confirmed_at = s.publications_for(1, 'led/state', 'ON')[0]['at']
    assert len(s.nodes[1].led_changes) == 1
    assert confirmed_at - physical_at > 50
    cases['lost_led_ack_no_immediate_reconciliation'] = {
        'modeled_rx_turnaround_seconds': 0.2, 'node_led_on_at': physical_at,
        'mqtt_on_at': confirmed_at, 'state_delay_seconds': round(confirmed_at - physical_at, 6), **s.summary()}

    s = Simulation({1: Node(1, valve=0)}, until=7, turnaround=lag)
    s.command(1, 1, 'valve', 'OPEN')
    s.run()
    pending = s.publications_for(1, 'valve/status')
    phases = [p['payload']['confirmation'] for p in pending]
    assert 'pending' in phases and 'unconfirmed' in phases
    assert s.publications_for(1, 'valve/state', 'open')
    assert len(s.nodes[1].pulses) == 1
    cases['lost_valve_ack_then_query'] = {'confirmation_phases': phases,
                                       'gpio_pulses_in_model': 1, **s.summary()}

    # Re-clicking generates NEW sequence numbers, distinct from radio retries.
    s = Simulation({1: Node(1, valve=0)}, until=16, turnaround=lag)
    for at in (1, 1.2, 1.4):
        s.command(at, 1, 'valve', 'OPEN')
    s.run()
    sequences = [p['sequence'] for p in s.nodes[1].pulses]
    assert len(sequences) == 3 and len(set(sequences)) == 3
    cases['three_reclicks_repeat_gpio'] = {'distinct_pulse_sequences': sequences, **s.summary()}

    # Healthy first command reaches the modeled node without a warmup gate.
    s = Simulation({1: Node(1)}, until=3)
    s.command(0.3, 1, 'led', 'ON')
    s.command(1, 1, 'valve', 'OPEN')
    s.run()
    assert s.publications_for(1, 'led/state', 'ON')[0]['at'] < 0.5
    assert s.publications_for(1, 'valve/state', 'open')[0]['at'] < 1.3
    assert len(s.nodes[1].pulses) == 1
    cases['healthy_first_commands'] = s.summary()
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Save public trace JSON')
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    cases = characterize()
    result = {'date': '2026-10-06', 'passed': True, 'scenario_count': len(cases),
              'real_controller': 'Bridge.run() and MQTT command/publication handlers',
              'node_and_radio': 'Explicit application/timing model, not physical emulation',
              'frontend_simulated': False, 'hardware_connected': False,
              'rf_airtime_seconds_assumed': AIRTIME,
              'source_sha256': {str(p.relative_to(ROOT_DIR)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (APP/'bridge.py', APP/'radio.py', APP/'protocol.py',
                                          ROOT_DIR/'firmware/libraries/ChacaicoNode/src/ChacaicoNode.h',
                                          ROOT_DIR/'firmware/nodes/node_1/node_1.ino',
                                          ROOT_DIR/'firmware/nodes/node_2/node_2.ino')},
              'cases': cases}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': True, 'scenarios': list(cases),
                      'late_power_on_delay': cases['late_power_on']['discovery_delay_seconds'],
                      'offline_peer_command_delay': cases['offline_peer_delay']['delay_seconds'],
                      'lost_led_ack_state_delay': cases['lost_led_ack_no_immediate_reconciliation']['state_delay_seconds'],
                      'reclick_gpio_pulses': len(cases['three_reclicks_repeat_gpio']['distinct_pulse_sequences'])}, indent=2))


if __name__ == '__main__':
    main()
