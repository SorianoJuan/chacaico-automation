"""Offline checks: no MQTT connection, radio transmission or physical GPIO."""
import importlib.util
from pathlib import Path
import queue
import sys
import tempfile
import types
import unittest

BRIDGE_DIR = Path(__file__).resolve().parents[1] / "bridge/chacaico_lora_bridge"
sys.path.insert(0, str(BRIDGE_DIR))
if importlib.util.find_spec("paho") is None:
    for name in ("paho", "paho.mqtt", "paho.mqtt.client"):
        sys.modules[name] = types.ModuleType(name)
sys.modules["radio"] = types.SimpleNamespace(Radio=object)
from bridge import Bridge, ROOT, POLL_INTERVAL
from protocol import encode, decode, GET_LED, SET_LED, SET_VALVE, GET_VALVE, VALVE_UNKNOWN


class ValveBridgeTest(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(16))
        self.bridge = Bridge.__new__(Bridge)
        self.bridge.nodes = {1: self.key}
        self.bridge.commands = queue.Queue(32)
        self.bridge.seen = {}
        self.bridge.valve_seen = {}
        self.bridge.status = {}
        self.bridge.last_ack = {}
        self.bridge.next_poll = {(1, op): 0 for op in (GET_VALVE, GET_LED)}
        self.bridge.last_was_poll = False
        self.bridge.pending = None
        self.bridge.sequence = 0
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.bridge.counter_file = Path(scratch.name) / 'sequence.json'
        self.published = []
        self.bridge.publish = lambda topic, value: self.published.append((topic, value))

    def message(self, topic, payload, retain=False):
        self.bridge.on_message(None, None, types.SimpleNamespace(
            topic=topic, payload=payload.encode(), retain=retain))

    def request(self, op=SET_VALVE, value=1):
        self.bridge.pending = {"node": 1, "seq": 42, "op": op, "value": value}

    def response(self, op, value, seq=42):
        self.bridge.accept_response((encode(self.key, 1, 1, seq, op, value), -55, 9), 100)

    def test_commands_are_explicit_and_retained_orders_are_ignored(self):
        base = ROOT + "/node/1"
        self.message(base + "/valve/set", "OPEN", retain=True)
        self.message(base + "/valve/set", "ON")
        self.message(base + "/other/set", "OPEN")
        self.message(ROOT + "/node/2/valve/set", "OPEN")
        self.assertTrue(self.bridge.commands.empty())
        self.message(base + "/valve/set", "OPEN")
        self.message(base + "/valve/set", "CLOSE")
        self.assertEqual(self.bridge.commands.get()[:3], (1, SET_VALVE, 1))
        self.assertEqual(self.bridge.commands.get()[:3], (1, SET_VALVE, 0))

    def test_wrong_ack_never_updates_state(self):
        self.request()
        self.response(SET_LED, 1)
        self.response(SET_VALVE, 0)
        self.response(SET_VALVE, 1, seq=41)
        self.assertEqual(self.published, [])
        self.assertIsNotNone(self.bridge.pending)
        self.response(SET_VALVE, 1)
        self.assertIn((ROOT + "/node/1/valve/state", "open"), self.published)
        self.assertIsNone(self.bridge.pending)

    def test_reboot_unknown_does_not_claim_valve_closed(self):
        self.request(GET_VALVE, 0)
        self.response(GET_VALVE, VALVE_UNKNOWN)
        self.assertIn((ROOT + "/node/1/valve/state", "None"), self.published)
        self.assertNotIn((ROOT + "/node/1/valve/state", "closed"), self.published)
        self.assertNotIn((ROOT + "/node/1/led/state", "ON"), self.published)

    def test_authenticated_frame_tampering_and_unknown_rules(self):
        frame = encode(self.key, 0, 1, 42, SET_VALVE, 1)
        for bit in range(160):
            damaged = bytearray(frame)
            damaged[bit // 8] ^= 1 << (bit % 8)
            with self.assertRaises(ValueError):
                decode(self.key, damaged)
        for kind, op, value in ((0, SET_VALVE, 2), (1, SET_VALVE, 2), (0, GET_VALVE, 1)):
            with self.assertRaises(ValueError):
                decode(self.key, encode(self.key, kind, 1, 42, op, value))
        self.assertEqual(decode(self.key, encode(self.key, 1, 1, 42, GET_VALVE, 2))[-1], 2)

    def test_two_nodes_route_commands_and_reject_each_others_acks(self):
        key2 = bytes(range(16, 32))
        self.bridge.nodes[2] = key2
        for node in (1, 2):
            self.message(f'{ROOT}/node/{node}/led/set', 'ON')
            self.message(f'{ROOT}/node/{node}/valve/set', 'CLOSE')
        self.assertEqual([self.bridge.commands.get()[:3] for _ in range(4)],
                         [(1, SET_LED, 1), (1, SET_VALVE, 0),
                          (2, SET_LED, 1), (2, SET_VALVE, 0)])
        self.bridge.pending = {'node': 2, 'seq': 42, 'op': SET_LED, 'value': 1}
        for key, node in ((self.key, 1), (self.key, 2), (key2, 1)):
            self.bridge.accept_response((encode(key, 1, node, 42, SET_LED, 1), -55, 9), 100)
        self.assertEqual(self.published, [])
        self.bridge.accept_response((encode(key2, 1, 2, 42, SET_LED, 1), -55, 9), 100)
        self.assertIn((ROOT + '/node/2/led/state', 'ON'), self.published)
        self.assertNotIn((ROOT + '/node/1/led/state', 'ON'), self.published)

    def test_led_activity_cannot_postpone_valve_poll(self):
        self.bridge.seen[1] = self.bridge.valve_seen[1] = 0
        self.bridge.next_poll[(1, GET_VALVE)] = 60
        for now in (20, 40, 59):
            self.request(SET_LED, 1)
            self.bridge.accept_response((encode(self.key, 1, 1, 42, SET_LED, 1), -55, 9), now)
            self.assertEqual(self.bridge.next_poll[(1, GET_VALVE)], 60)
        self.bridge.commands.put((1, SET_LED, 0, 60))
        self.assertEqual(self.bridge.next_request(60), (1, GET_VALVE, 0))

    def test_continuous_led_commands_keep_both_valves_fresh(self):
        b = self.bridge
        b.nodes[2] = bytes(range(16, 32))
        b.next_poll = {(node, op): 0 for node in b.nodes for op in (GET_VALVE, GET_LED)}
        valve_polls = {1: [], 2: []}
        commands = 0
        for now in range(181):
            b.commands.put((1 if now % 2 == 0 else 2, SET_LED, now % 2, now))
            request = b.next_request(now)
            self.assertIsNotNone(request)
            node, op, value = request
            b.start_request(*request, now=now)
            if op == GET_VALVE:
                valve_polls[node].append(now)
                response_value = VALVE_UNKNOWN
            else:
                response_value = value
                commands += op == SET_LED
            frame = encode(b.nodes[node], 1, node, b.pending['seq'], op, response_value)
            b.accept_response((frame, -55, 9), now)
            b.expire_nodes(now)
        for node, times in valve_polls.items():
            self.assertGreaterEqual(len(times), 3)
            self.assertTrue(all(right - left <= POLL_INTERVAL + 4 for left, right in zip(times, times[1:])))
            self.assertNotIn((f'{ROOT}/node/{node}/valve/availability', 'offline'), self.published)
        self.assertGreater(commands, 100)

    def test_led_recovery_queries_valve_without_claiming_its_position(self):
        self.bridge.seen[1] = self.bridge.valve_seen[1] = 0
        self.bridge.next_poll[(1, GET_VALVE)] = 500
        self.request(SET_LED, 1)
        self.bridge.accept_response((encode(self.key, 1, 1, 42, SET_LED, 1), -55, 9), 100)
        self.bridge.expire_nodes(100)
        self.assertIn((ROOT + '/node/1/availability', 'online'), self.published)
        self.assertIn((ROOT + '/node/1/valve/availability', 'offline'), self.published)
        self.assertEqual(self.bridge.next_request(100), (1, GET_VALVE, 0))
        self.request(GET_VALVE, 0)
        self.response(GET_VALVE, VALVE_UNKNOWN)
        self.assertIn((ROOT + '/node/1/valve/availability', 'online'), self.published)
        self.assertIn((ROOT + '/node/1/valve/state', 'None'), self.published)
        self.assertNotIn((ROOT + '/node/1/valve/state', 'closed'), self.published)

    def test_offline_peer_and_failed_led_do_not_delay_other_work(self):
        b = self.bridge
        b.commands.put((1, SET_LED, 1, 0))
        request = b.next_request(0)
        self.assertEqual(request, (1, GET_VALVE, 0))
        b.start_request(*request, now=0)
        b.request_failed(3)
        self.assertEqual(b.next_request(3), (1, SET_LED, 1))
        valve_due = b.next_poll[(1, GET_VALVE)]
        self.request(GET_LED, 0)
        b.request_failed(4)
        self.assertEqual(b.next_poll[(1, GET_VALVE)], valve_due)

    def test_valve_timeout_does_not_invent_a_closed_position(self):
        b = self.bridge
        self.request(SET_VALVE, 0)
        b.request_failed(10)
        self.assertEqual(b.next_poll[(1, GET_VALVE)], 10)
        self.assertIn((ROOT + '/node/1/valve/state', 'None'), self.published)
        self.assertNotIn((ROOT + '/node/1/valve/state', 'closed'), self.published)

    def test_broker_reconnect_requests_fresh_valve_states(self):
        b = self.bridge
        b.next_poll[(1, GET_VALVE)] = 1000
        client = types.SimpleNamespace(subscribe=lambda *args, **kwargs: None)
        b.on_connect(client, None, None, types.SimpleNamespace(is_failure=False), None)
        self.assertEqual(b.next_poll[(1, GET_VALVE)], 0)
        self.assertIn((ROOT + '/node/1/valve/state', 'None'), self.published)
        self.assertEqual(b.next_request(100), (1, GET_VALVE, 0))


if __name__ == "__main__":
    unittest.main()
