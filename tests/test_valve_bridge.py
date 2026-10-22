"""Fault-injection tests for the actual scheduler and authenticated protocol."""
import dataclasses
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge/chacaico_lora_bridge"))
from engine import Engine, Sequence, ROOT
from protocol import *


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.clock = 100.
        self.output = []
        self.keys = {1: bytes(range(16)), 2: bytes(range(16, 32))}
        self.engine = self.create()

    def create(self):
        return Engine(self.keys, self.scratch.name, lambda t, v: self.output.append((t, v)),
                      lambda: self.clock, lambda: 1800000000 + self.clock)

    def ready(self, node=1, boot=1, wake=1, sleep=0, revision=1, pulse=50):
        f = Frame(READY, node, boot, wake, 0, revision=revision, sleep_s=sleep, pulse_ms=pulse, valve=UNKNOWN)
        self.engine.receive(encode(self.keys[node], f), -50, 12)
        self.clock += .2
        return f

    def request(self):
        outgoing = self.engine.next_frame()
        self.assertIsNotNone(outgoing)
        node, packet = outgoing
        f = decode(self.keys[node], packet)
        self.engine.sent(node)
        return f

    def respond(self, request, **values):
        n = self.engine.nodes[request.node]
        reported = {"revision": n.advertised["revision"], "sleep_s": n.advertised["sleep_s"],
                    "pulse_ms": n.advertised["pulse_ms"], "valve": UNKNOWN, "led": 0}
        if request.op == SET_CONFIG:
            reported.update(revision=request.revision, sleep_s=request.sleep_s, pulse_ms=request.pulse_ms)
        if request.op == SET_VALVE:
            reported["valve"] = request.valve
        if request.op == SET_LED:
            reported["led"] = request.led
        reported.update(values)
        f = dataclasses.replace(request, kind=RESPONSE, **reported)
        self.clock += .3
        self.engine.receive(encode(self.keys[f.node], f), -50, 12)
        self.clock += .3
        return f

    def connect(self, **kwargs):
        self.ready(**kwargs)
        request = self.request()
        self.assertEqual(request.op, GET_CONFIG)
        self.respond(request)

    def apply(self, sleep=5, pulse=50, node=1):
        self.engine.message(node, "config/sleep_s/set", str(sleep))
        self.engine.message(node, "config/pulse_ms/set", str(pulse))
        self.engine.message(node, "config/apply", "APPLY")

    def has(self, suffix, value, node=1):
        return (f"{ROOT}/node/{node}/{suffix}", value) in self.output

    def test_storage_error_remains_visible_until_explicit_query(self):
        self.connect();self.apply();self.respond(self.request())
        self.respond(self.request(), status=STORE_FAILED, revision=1, sleep_s=0, pulse_ms=50)
        self.assertEqual(self.engine.nodes[1].config_status, "Error de memoria")
        self.clock += 31
        self.respond(self.request())
        self.assertEqual(self.engine.nodes[1].config_status, "Error de memoria")
        self.engine = self.create()
        self.assertEqual(self.engine.nodes[1].config_status, "Error de memoria")
        self.ready(wake=2)
        self.engine.message(1, "config/query", "QUERY")
        self.respond(self.request())
        self.assertEqual(self.engine.nodes[1].config_status, "Confirmada")

    def test_reconnect_initializes_command_status(self):
        self.engine.reconnect()
        self.assertTrue(self.has("command/status", "Sin órdenes pendientes"))
        self.engine.message(1, "led/set", "ON")
        self.engine.reconnect()
        self.assertEqual(self.engine.nodes[1].command_status, "Pendiente")

    def test_window_end_reconciles_uncertain_actuation(self):
        self.connect(sleep=5)
        self.engine.message(1, "led/set", "ON")
        self.request()
        self.clock += 3
        self.engine.tick()
        self.assertTrue(self.engine.nodes[1].reconcile)
        self.ready(wake=2, sleep=5)
        self.assertEqual(self.request().op, GET_CONFIG)

    def test_valve_status_survives_led_ack_and_unrelated_reports(self):
        self.connect()
        self.engine.message(1, "valve/set", "OPEN")
        self.engine.message(1, "led/set", "ON")
        n = self.engine.nodes[1]
        f = Frame(RESPONSE, 1, n.boot, n.wake, 1, SET_LED,
                  revision=1, pulse_ms=50, valve=0, led=1)
        self.engine.report(n, f, -50, 12)
        self.assertEqual(n.action_status[SET_VALVE], "Pendiente")
        self.assertEqual(n.action_status[SET_LED], "Confirmada")
        self.assertEqual(self.engine.published[f"{ROOT}/node/1/valve/command/status"], "Pendiente")
        self.engine.reconnect()
        self.assertEqual(self.engine.published[f"{ROOT}/node/1/valve/command/status"], "Pendiente")
        self.respond(self.request())
        self.assertEqual(n.action_status[SET_VALVE], "Confirmada")

    def test_expired_valve_status_survives_telemetry_and_led_command(self):
        self.connect(sleep=30)
        self.respond(self.request())  # close listening window
        self.engine.message(1, "valve/set", "OPEN")
        self.clock += 51
        self.engine.tick()
        n = self.engine.nodes[1]
        self.assertEqual(n.action_status[SET_VALVE], "Vencida sin confirmar")
        self.ready(wake=2, sleep=30)
        self.respond(self.request(), valve=0)
        self.engine.message(1, "led/set", "ON")
        self.respond(self.request(), valve=0)
        self.assertEqual(n.action_status[SET_VALVE], "Vencida sin confirmar")
        self.engine.message(1, "valve/set", "OPEN")
        self.assertEqual(n.action_status[SET_VALVE], "Pendiente")

    def test_restart_does_not_replay_or_claim_confirmed_valve_command(self):
        self.connect();self.engine.message(1, "valve/set", "OPEN")
        self.engine = self.create();self.engine.reconnect()
        self.assertFalse(self.engine.nodes[1].actions)
        self.assertEqual(self.engine.published[f"{ROOT}/node/1/valve/command/status"], "Sin órdenes pendientes")

    def test_all_frame_bits_are_authenticated(self):
        packet = encode(self.keys[1], Frame(REQUEST, 1, 1, 1, 1, SET_LED, led=1))
        self.assertEqual(len(packet), FRAME_SIZE)
        for bit in range(len(packet)*8):
            bad = bytearray(packet);bad[bit//8] ^= 1 << (bit%8)
            with self.assertRaises(ValueError): decode(self.keys[1], bad)
        with self.assertRaises(ValueError): decode(self.keys[2], packet)

    def test_initial_ready_requires_query_before_confirmed(self):
        self.ready()
        self.assertFalse(self.engine.nodes[1].verified)
        self.assertFalse(self.has("config/status", "Confirmada"))
        self.respond(self.request())
        self.assertTrue(self.engine.nodes[1].verified)
        self.assertTrue(self.has("valve/state", "None"))
        self.assertFalse(self.has("valve/state", "closed"))

    def test_editing_only_changes_draft(self):
        self.connect()
        self.engine.message(1, "config/sleep_s/set", "5")
        self.assertIsNone(self.engine.next_frame())
        self.assertEqual(self.engine.nodes[1].confirmed["sleep_s"], 0)
        self.assertEqual(self.engine.nodes[1].draft["sleep_s"], 5)

    def test_apply_is_atomic_and_confirmed_only_after_matching_ack(self):
        self.connect();self.apply(5, 75)
        self.respond(self.request())  # Read baseline before choosing revision.
        req = self.request()
        self.assertEqual((req.op, req.revision, req.sleep_s, req.pulse_ms), (SET_CONFIG, 2, 5, 75))
        self.assertEqual(self.engine.nodes[1].confirmed["sleep_s"], 0)
        self.respond(req)
        self.assertEqual(self.engine.nodes[1].confirmed["sleep_s"], 5)
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.request().op, END)

    def test_lost_config_ack_recovers_via_query_without_new_revision(self):
        self.connect();self.apply();self.respond(self.request())
        req = self.request()
        for _ in range(2):
            self.clock += 1.6
            retry = self.request()
            self.assertEqual(retry, req)
        self.clock += 1.6
        self.engine.tick()
        self.clock += 1.1
        query = self.request()
        self.assertEqual(query.op, GET_CONFIG)
        self.respond(query, revision=2, sleep_s=5)
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.engine.nodes[1].config_status, "Confirmada")

    def test_pending_config_survives_bridge_restart(self):
        self.connect();self.apply(7, 60)
        self.engine = self.create()
        self.assertEqual(self.engine.nodes[1].config_job["sleep_s"], 7)
        self.assertFalse(self.engine.nodes[1].verified)
        self.ready(wake=2)
        self.respond(self.request())
        request = self.request()
        self.assertEqual((request.sleep_s, request.pulse_ms), (7, 60))

    def test_restart_after_lost_ack_reads_effective_config(self):
        self.connect();self.apply();self.respond(self.request());self.request()
        self.engine = self.create()
        self.ready(boot=2, sleep=5, revision=2)
        self.respond(self.request())
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.engine.nodes[1].confirmed["revision"], 2)

    def test_old_session_cannot_confirm_or_reopen_window(self):
        self.connect(sleep=5)
        request = self.request()  # END
        self.respond(request)
        self.ready(wake=1, sleep=5)
        self.assertTrue(self.engine.nodes[1].closed)
        self.ready(wake=2, sleep=5)
        current = self.request()
        before = len(self.output)
        self.respond(dataclasses.replace(current, wake=1))
        self.assertEqual(len(self.output), before)
        self.assertIsNotNone(self.engine.nodes[1].pending)

    def test_boot_rollback_is_rejected_after_bridge_restart(self):
        self.connect(boot=4)
        self.engine = self.create()
        self.ready(boot=3)
        self.assertEqual(self.engine.nodes[1].boot, 4)
        self.assertEqual(self.engine.nodes[1].wake, 0)

    def test_wrong_node_key_sequence_and_operation_never_ack(self):
        self.connect()
        self.engine.message(1, "led/set", "ON")
        req = self.request()
        before = len(self.output)
        for change in ({"node": 2}, {"boot": 2}, {"wake": 2}, {"sequence": req.sequence+1}, {"op": SET_VALVE}):
            f = dataclasses.replace(req, kind=RESPONSE, revision=1, pulse_ms=50, **change)
            self.engine.receive(encode(self.keys[f.node], f), -50, 12)
        self.assertEqual(len(self.output), before)
        self.assertIsNotNone(self.engine.nodes[1].pending)

    def test_both_node_pulse_limits_and_persistence(self):
        for node in (1, 2):
            self.connect(node=node)
            self.apply(sleep=30, pulse=3000, node=node)
        self.engine = self.create()
        for node in (1, 2):
            with self.subTest(node=node):
                self.assertEqual(self.engine.nodes[node].config_job["pulse_ms"], 3000)
                self.assertEqual(self.engine.nodes[node].draft["pulse_ms"], 3000)
                for pulse in (10, 50, 200, 3000):
                    self.assertTrue(valid_config(0, pulse, node=node))
                    frame = Frame(READY, node, 1, 1, 0, revision=1, pulse_ms=pulse)
                    self.assertEqual(decode(self.keys[node], encode(self.keys[node], frame)), frame)
                for pulse in (9, 3001):
                    self.engine.message(node, "config/pulse_ms/set", str(pulse))
                    self.assertEqual(self.engine.nodes[node].draft["pulse_ms"], 3000)
                    self.assertFalse(valid_config(0, pulse, node=node))
        self.assertFalse(valid_config(0, 201, node=3))
        with self.assertRaises(ValueError):
            decode(self.keys[2], encode(self.keys[2], Frame(
                READY, 3, 1, 1, 0, revision=1, pulse_ms=3000)))

    def test_long_pulse_ack_keeps_pending_and_radio_receive_window(self):
        self.connect(sleep=30, pulse=3000)
        self.engine.message(1, "valve/set", "OPEN")
        request = self.request()
        sent_at = self.clock
        self.clock += 3.1
        self.engine.tick()
        self.assertIsNotNone(self.engine.nodes[1].pending)
        self.assertFalse(self.has("valve/command/status", "Confirmada"))
        self.assertIsNone(self.engine.next_frame())  # No TX over the delayed valve ACK.
        self.respond(request)
        self.assertTrue(self.has("valve/command/status", "Confirmada"))
        self.assertFalse(self.engine.nodes[1].actions)
        self.assertGreater(self.engine.nodes[1].active_until, sent_at + 3.4)

    def test_lost_long_pulse_ack_retries_same_transaction(self):
        self.connect(sleep=30, pulse=3000)
        self.engine.message(1, "valve/set", "OPEN")
        first = self.request()
        self.clock += 4.51
        retry = self.request()
        self.assertEqual(first, retry)
        self.respond(retry)
        self.assertTrue(self.has("valve/command/status", "Confirmada"))

    def test_long_pulse_waits_for_next_wake_if_budget_is_insufficient(self):
        self.connect(sleep=30, pulse=3000)
        n = self.engine.nodes[1]
        n.hard_until = self.clock + 3.9
        self.engine.message(1, "valve/set", "OPEN")
        ending = self.request()
        self.assertEqual(ending.op, END)
        self.respond(ending)
        self.assertIn(SET_VALVE, n.actions)
        self.clock += 30
        self.ready(wake=2, sleep=30, pulse=3000)
        command = self.request()
        self.assertEqual(command.op, SET_VALVE)
        self.clock += 3
        self.respond(command)
        self.assertTrue(self.has("valve/command/status", "Confirmada"))

    def test_invalid_fields_and_retained_commands_do_not_apply(self):
        self.connect()
        for value in ("-1", "3601", "nan", "inf", "1.2", "five"):
            self.engine.message(1, "config/sleep_s/set", value)
        for value in ("0", "9", "3001", "nan"):
            self.engine.message(1, "config/pulse_ms/set", value)
        self.engine.message(1, "config/apply", "APPLY", True)
        self.engine.message(1, "valve/set", "OPEN", True)
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.engine.nodes[1].draft, CONFIG_DEFAULTS)
        self.assertFalse(self.engine.nodes[1].actions)

    def test_duplicate_clicks_coalesce_and_close_cancels_unsent_open(self):
        self.connect(sleep=5);self.respond(self.request())
        for _ in range(5): self.engine.message(1, "valve/set", "OPEN")
        self.assertEqual(len(self.engine.nodes[1].actions), 1)
        self.engine.message(1, "valve/set", "CLOSE")
        self.ready(wake=2, sleep=5)
        request = self.request()
        self.assertEqual((request.op, request.valve), (SET_VALVE, 0))

    def test_new_close_supersedes_inflight_open_ack(self):
        self.connect()
        self.engine.message(1, "valve/set", "OPEN");old = self.request()
        self.engine.message(1, "valve/set", "CLOSE")
        self.respond(old)
        self.assertFalse(self.has("valve/state", "open"))
        self.clock += .1  # The maximum-pulse RX guard also covers the superseded request.
        request = self.request()
        self.assertEqual((request.op, request.valve), (SET_VALVE, 0))
        self.assertGreater(request.sequence, old.sequence)

    def test_expired_open_is_not_executed_at_late_wake(self):
        self.connect(sleep=5);self.respond(self.request())
        self.engine.message(1, "valve/set", "OPEN")
        self.clock += 30;self.ready(wake=2, sleep=5)
        self.engine.tick()
        self.assertFalse(self.engine.nodes[1].actions)
        self.assertEqual(self.request().op, GET_CONFIG)
        self.assertTrue(self.has("command/status", "Vencida sin confirmar"))

    def test_expected_sleep_keeps_last_state_available(self):
        self.connect(sleep=120);self.respond(self.request())
        self.clock += 120;self.engine.tick()
        self.assertTrue(self.has("link/state", "Reposo esperado"))
        self.assertEqual(self.engine.published[f"{ROOT}/node/1/availability"], "online")
        self.clock += 400;self.engine.tick()
        self.assertEqual(self.engine.published[f"{ROOT}/node/1/availability"], "offline")

    def test_lost_end_ack_does_not_send_retries_into_sleep(self):
        self.connect(sleep=5)
        end = self.request()
        self.assertEqual(end.op, END)
        self.clock += 1.6;self.engine.tick()
        self.assertTrue(self.engine.nodes[1].closed)
        self.assertIsNone(self.engine.next_frame())

    def test_config_storage_failure_is_visible_and_not_confirmed(self):
        self.connect();self.apply();self.respond(self.request())
        req = self.request()
        self.respond(req, status=STORE_FAILED, revision=1, sleep_s=0)
        self.assertEqual(self.engine.nodes[1].config_status, "Error de memoria")
        self.assertEqual(self.engine.nodes[1].confirmed["revision"], 1)
        self.assertIsNone(self.engine.nodes[1].config_job)

    def test_conflict_refreshes_revision(self):
        self.connect();self.apply();self.respond(self.request())
        self.respond(self.request(), status=CONFLICT, revision=8, sleep_s=0)
        self.respond(self.request(), revision=8)
        req = self.request()
        self.assertEqual((req.op, req.revision), (SET_CONFIG, 9))

    def test_apply_twice_does_not_allocate_second_revision(self):
        self.connect();self.apply()
        first = dict(self.engine.nodes[1].config_job)
        self.clock += 1
        self.apply()
        self.assertEqual(self.engine.nodes[1].config_job, first)

    def test_same_configuration_is_a_noop(self):
        self.connect();self.apply(0, 50)
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertIsNone(self.engine.next_frame())

    def test_new_apply_during_previous_transaction_preserves_new_intent(self):
        self.connect();self.apply(5);self.respond(self.request());old = self.request()
        self.apply(9)
        self.respond(old)
        self.assertEqual(self.engine.nodes[1].config_job["sleep_s"], 9)
        self.respond(self.request())
        new = self.request()
        self.assertEqual((new.sleep_s, new.revision), (9, 3))

    def test_zero_sleep_returns_to_continuous_receive(self):
        self.connect(sleep=5)
        self.apply(0);self.respond(self.request())
        self.respond(self.request())
        n = self.engine.nodes[1]
        self.assertEqual(n.active_until, float("inf"))
        self.assertIsNone(self.engine.next_frame())

    def test_lost_led_ack_triggers_readback(self):
        self.connect();self.engine.message(1, "led/set", "ON")
        first = self.request()
        for _ in range(2):
            self.clock += 1.6;self.assertEqual(self.request(), first)
        self.clock += 1.6;self.engine.tick();self.clock += 1.1
        req = self.request();self.assertEqual(req.op, GET_CONFIG)
        self.respond(req, led=1)
        self.assertTrue(self.has("led/state", "ON"))
        self.assertNotIn(SET_LED, self.engine.nodes[1].actions)

    def test_sequence_reservation_survives_restart_without_reuse(self):
        path = Path(self.scratch.name)/"reserved.json"
        first = Sequence(path);a = first.next();b = first.next()
        self.assertEqual(b, a+1)
        second = Sequence(path)
        self.assertGreater(second.next(), b)
        path.write_text('"corrupted"')
        with self.assertRaises(ValueError): Sequence(path)

    def test_other_node_progresses_during_missing_ack(self):
        self.connect()
        self.ready(node=2)
        req = self.request();self.assertEqual(req.node, 2)
        self.clock += .5
        self.engine.message(1, "led/set", "ON")
        next_req = self.request()
        self.assertEqual(next_req.node, 1)
        self.respond(next_req)
        self.assertTrue(self.has("led/state", "ON"))

    def test_pending_commands_are_not_replayed_after_bridge_restart(self):
        self.connect();self.engine.message(1, "valve/set", "OPEN")
        self.engine = self.create()
        self.assertFalse(self.engine.nodes[1].actions)

    def test_outdated_config_job_expires_without_transmission(self):
        self.connect();self.apply()
        self.clock += 86401;self.engine.tick()
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.engine.nodes[1].config_status, "Vencida sin confirmar")

    def test_sleep_transition_after_long_continuous_run_has_fresh_window(self):
        self.connect();self.clock += 100
        self.apply();self.respond(self.request());self.respond(self.request())
        self.assertGreater(self.engine.nodes[1].active_until, self.clock)
        self.assertEqual(self.request().op, END)

    def test_long_pulse_ack_keeps_pending_and_radio_receive_window_node_two(self):
        self.connect(node=2, sleep=30, pulse=3000)
        self.engine.message(2, "valve/set", "OPEN")
        request = self.request()
        sent_at = self.clock
        self.clock += 3.1
        self.engine.tick()
        self.assertIsNotNone(self.engine.nodes[2].pending)
        self.assertFalse(self.has("valve/command/status", "Confirmada", node=2))
        self.assertIsNone(self.engine.next_frame())  # No TX over the delayed valve ACK.
        self.respond(request)
        self.assertTrue(self.has("valve/command/status", "Confirmada", node=2))
        self.assertFalse(self.engine.nodes[2].actions)
        self.assertGreater(self.engine.nodes[2].active_until, sent_at + 3.4)

    def test_lost_long_pulse_ack_retries_same_transaction_node_two(self):
        self.connect(node=2, sleep=30, pulse=3000)
        self.engine.message(2, "valve/set", "OPEN")
        first = self.request()
        self.clock += 4.51
        retry = self.request()
        self.assertEqual(first, retry)
        self.respond(retry)
        self.assertTrue(self.has("valve/command/status", "Confirmada", node=2))

    def test_long_pulse_waits_for_next_wake_if_budget_is_insufficient_node_two(self):
        self.connect(node=2, sleep=30, pulse=3000)
        n = self.engine.nodes[2]
        n.hard_until = self.clock + 3.9
        self.engine.message(2, "valve/set", "OPEN")
        ending = self.request()
        self.assertEqual(ending.op, END)
        self.respond(ending)
        self.assertIn(SET_VALVE, n.actions)
        self.clock += 30
        self.ready(node=2, wake=2, sleep=30, pulse=3000)
        command = self.request()
        self.assertEqual(command.op, SET_VALVE)
        self.clock += 3
        self.respond(command)
        self.assertTrue(self.has("valve/command/status", "Confirmada", node=2))

if __name__ == "__main__":
    unittest.main()
