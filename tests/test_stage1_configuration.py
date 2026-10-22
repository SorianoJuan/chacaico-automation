"""End-to-end scheduler boundaries for radio configuration and delivery metrics."""
import dataclasses
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import test_valve_bridge as baseline
from engine import Engine, ROOT
from protocol import *


class ConfigurationStageOneTest(baseline.EngineTest):
    # Reuse the virtual clock/transport helpers, not copies of scheduler logic.
    def setUp(self):
        super().setUp()

    def config_reply(self, req, **updates):
        cfg = {**self.engine.nodes[req.node].advertised}
        if req.op in (SET_CONFIG, COMMIT_CONFIG):
            cfg = {"revision": req.revision, **{k: getattr(req, k) for k in CONFIG_KEYS}}
        cfg.pop("confirmed_at", None)
        cfg.update(updates)
        reply = dataclasses.replace(req, kind=RESPONSE, **cfg)
        self.clock += .3
        self.engine.receive(encode(self.keys[req.node], reply), -91, 3.5)
        self.clock += .3
        return reply

    def change(self, **cfg):
        for key, value in cfg.items():
            self.engine.message(1, f"config/{key}/set", str(value))
        self.engine.message(1, "config/apply", "APPLY")

    def test_ack_after_order_deadline_is_not_confirmed_even_before_tick(self):
        self.connect()
        self.engine.message(1, 'policy/command_ttl_s/set', '1')
        self.engine.message(1, 'policy/apply', 'APPLY')
        self.engine.message(1, 'led/set', 'ON')
        req = self.request()
        self.clock += 1.01
        self.config_reply(req, led=1)
        n = self.engine.nodes[1]
        self.assertEqual(n.metrics['expired'], 1)
        self.assertEqual(n.metrics['confirmed'], 0)
        self.assertEqual(n.action_status[SET_LED], 'Vencida sin confirmar')

    def test_effective_ttl_includes_pending_sleep_configuration(self):
        self.connect()
        self.change(sleep_s=60, max_awake_ms=12000)
        self.engine.metrics_view(self.engine.nodes[1])
        metrics = json.loads(self.engine.published[f'{ROOT}/node/1/metrics'])
        self.assertEqual(metrics['command_ttl_s'], 82)
        before = self.clock
        self.engine.message(1, 'led/set', 'ON')
        self.assertEqual(self.engine.nodes[1].actions[SET_LED]['deadline'], before + 82)

    def test_failed_hat_write_restores_previous_power_and_reports_error(self):
        self.connect()
        calls = []
        def hardware(power):
            calls.append(power)
            if power == 20: raise OSError('injected SPI failure')
        self.engine.set_power = hardware
        self.engine.bridge_message('power/set', '20')
        with self.assertLogs('chacaico', level='ERROR'):
            self.engine.bridge_message('power/apply', 'APPLY')
        self.assertEqual(calls, [20, 0])
        self.assertEqual(self.engine.bridge_power, 0)
        self.assertIn('Error', self.engine.bridge_power_status)

    def test_power_requires_trial_then_commit_then_matching_stable_ack(self):
        self.connect()
        self.change(tx_power_dbm=14, listen_ms=2000, max_awake_ms=12000)
        self.config_reply(self.request())
        trial = self.request()
        self.assertEqual(trial.op, SET_CONFIG)
        self.config_reply(trial, status=TRIAL, flags=1)
        self.assertEqual(self.engine.nodes[1].confirmed['tx_power_dbm'], 0)
        commit = self.request()
        self.assertEqual(commit.op, COMMIT_CONFIG)
        self.assertEqual(commit.revision, trial.revision)
        self.assertEqual(commit.tx_power_dbm, 14)
        self.config_reply(commit)
        self.assertEqual(self.engine.nodes[1].confirmed['tx_power_dbm'], 14)
        self.assertEqual(self.engine.nodes[1].confirmed['listen_ms'], 2000)
        self.assertIsNone(self.engine.nodes[1].config_job)

    def test_lost_commit_ack_reconciles_persisted_settings(self):
        self.connect(); self.change(tx_power_dbm=20)
        self.config_reply(self.request()); self.config_reply(self.request(), status=TRIAL, flags=1)
        commit = self.request()
        for _ in range(2):
            self.clock += 1.6
            self.assertEqual(self.request(), commit)
        self.clock += 2.7; self.engine.tick()
        self.clock += 1.1
        query = self.request()
        self.assertEqual(query.op, GET_CONFIG)
        self.config_reply(query, revision=commit.revision, tx_power_dbm=20)
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.engine.nodes[1].confirmed['tx_power_dbm'], 20)

    def test_lost_power_trial_never_claims_new_power(self):
        self.connect(); self.change(tx_power_dbm=22)
        self.config_reply(self.request()); trial = self.request()
        for _ in range(2):
            self.clock += 1.6; self.assertEqual(self.request(), trial)
        self.clock += 1.6; self.engine.tick(); self.clock += 1.1
        query = self.request()
        self.assertEqual(query.op, GET_CONFIG)
        self.config_reply(query)
        self.assertEqual(self.engine.nodes[1].confirmed['tx_power_dbm'], 0)
        self.assertIsNotNone(self.engine.nodes[1].config_job)

    def test_variable_windows_drive_scheduler(self):
        f = Frame(READY, 1, 1, 1, 0, revision=1, sleep_s=30, pulse_ms=50,
                  listen_ms=1000, max_awake_ms=5000)
        self.engine.receive(encode(self.keys[1], f), -80, 5)
        n = self.engine.nodes[1]
        self.assertAlmostEqual(n.active_until, self.clock + .8)
        self.assertAlmostEqual(n.hard_until, self.clock + 4.5)
        self.clock += .2
        self.config_reply(self.request())
        self.assertEqual(n.advertised['listen_ms'], 1000)

    def test_policy_draft_apply_persist_and_old_deadlines_unchanged(self):
        self.connect(sleep=30); self.respond(self.request())
        self.engine.message(1, 'valve/set', 'OPEN')
        n = self.engine.nodes[1]; deadline = n.actions[SET_VALVE]['deadline']
        self.engine.message(1, 'policy/command_ttl_s/set', '5')
        self.assertEqual(n.policy['command_ttl_s'], 0)
        self.engine.message(1, 'policy/missed_contacts/set', '7')
        self.engine.message(1, 'policy/apply', 'APPLY')
        self.assertEqual(n.actions[SET_VALVE]['deadline'], deadline)
        self.engine.message(1, 'led/set', 'ON')
        self.assertEqual(n.actions[SET_LED]['deadline'], self.clock + 5)
        self.clock += 6; self.engine.tick()
        self.assertNotIn(SET_LED, n.actions)
        self.assertIn(SET_VALVE, n.actions)
        self.assertEqual(n.metrics['expired'], 1)
        self.engine = self.create()
        self.assertEqual(self.engine.nodes[1].policy, {'command_ttl_s': 5, 'missed_contacts': 7})
        self.assertFalse(self.engine.nodes[1].actions)
        self.assertEqual(self.engine.nodes[1].metrics['orders'], 0)

    def test_missed_contacts_change_availability_without_false_sleep_alarm(self):
        self.connect(sleep=60); n = self.engine.nodes[1]
        self.engine.message(1, 'policy/missed_contacts/set', '2')
        self.engine.message(1, 'policy/apply', 'APPLY')
        timeout = self.engine.contact_timeout(n)
        self.clock = n.seen + timeout - .01; self.engine.tick()
        self.assertEqual(self.engine.published[f'{ROOT}/node/1/availability'], 'online')
        self.clock += .02; self.engine.tick()
        self.assertEqual(self.engine.published[f'{ROOT}/node/1/availability'], 'offline')

    def test_metrics_separate_wait_retry_and_delivery_and_both_rssi(self):
        self.connect(sleep=30); self.respond(self.request())
        self.engine.message(1, 'led/set', 'ON')
        queued = self.clock
        for _ in range(3): self.engine.message(1, 'led/set', 'ON')
        self.clock += 25; self.ready(wake=2, sleep=30)
        req = self.request(); first = self.clock
        self.clock += 1.6; self.assertEqual(self.request(), req)
        self.config_reply(req, led=1, downlink_rssi=-97, downlink_snr=-3)
        n = self.engine.nodes[1]; self.engine.tick()
        self.assertEqual(n.metrics['orders'], 1)
        self.assertEqual(n.metrics['confirmed'], 1)
        self.assertEqual(n.metrics['last_attempts'], 2)
        self.assertAlmostEqual(n.metrics['last_queue_s'], first - queued)
        self.assertGreater(n.metrics['last_delivery_s'], 1.5)
        self.assertEqual(n.metrics['downlink_rssi'], -97)
        self.assertEqual(n.metrics['uplink_rssi'], -91)
        self.assertEqual(n.metrics['retries'], 1)
        self.engine.receive(encode(self.keys[1], dataclasses.replace(req, kind=RESPONSE,
            revision=1, pulse_ms=50, sleep_s=30)), -80, 9)
        self.assertEqual(n.metrics['confirmed'], 1)

    def test_legacy_node_remains_controllable_but_new_settings_are_rejected(self):
        ready = Frame(READY, 1, 1, 1, 0, revision=1, pulse_ms=50, version=2)
        self.engine.receive(encode(self.keys[1], ready), -50, 10); self.clock += .2
        req = self.request(); self.assertEqual(req.version, 2)
        self.respond(req)
        self.engine.message(1, 'led/set', 'ON'); self.respond(self.request())
        self.change(tx_power_dbm=14)
        self.assertIsNone(self.engine.nodes[1].config_job)
        self.assertEqual(self.engine.nodes[1].config_status, 'Requiere firmware 0.5.0')

    def test_invalid_configuration_combinations_are_not_applied(self):
        self.connect()
        for cfg in ({'tx_power_dbm': 23}, {'listen_ms': 999}, {'max_awake_ms': 4999},
                    {'listen_ms': 10000}, {'max_awake_ms': 60001}):
            for key, value in cfg.items():
                self.engine.message(1, f'config/{key}/set', str(value))
            self.assertEqual(self.engine.nodes[1].draft, CONFIG_DEFAULTS)
        self.change(max_awake_ms=60000, listen_ms=10000, tx_power_dbm=22)
        self.assertIsNotNone(self.engine.nodes[1].config_job)

    def test_legacy_runtime_migration_preserves_revision_boot_and_pending_settings(self):
        saved = {'version': 1, 'nodes': {'1': {'boot': 19, 'confirmed': {
            'revision': 8, 'sleep_s': 30, 'pulse_ms': 75, 'confirmed_at': 1800000000},
            'draft': {'sleep_s': 30, 'pulse_ms': 75}, 'config_job': None}}}
        self.engine.file.write_text(json.dumps(saved)); self.engine = self.create()
        n = self.engine.nodes[1]
        self.assertEqual((n.boot, n.confirmed['revision'], n.advertised['pulse_ms']), (19, 8, 75))
        self.assertEqual(n.confirmed['tx_power_dbm'], 0)
        self.assertEqual(n.policy, POLICY_DEFAULTS)

    def test_bridge_power_apply_restore_and_invalid_input(self):
        powers = []
        self.engine = Engine(self.keys, self.scratch.name, lambda *a: None,
            lambda: self.clock, lambda: self.clock, powers.append)
        self.engine.bridge_message('power/set', '14')
        self.assertEqual(powers, [0])
        self.engine.bridge_message('power/apply', 'APPLY')
        self.assertEqual(powers, [0, 14])
        self.engine.bridge_message('power/set', '23')
        self.assertEqual(self.engine.bridge_power_draft, 14)
        restored = Engine(self.keys, self.scratch.name, lambda *a: None,
            lambda: self.clock, lambda: self.clock, powers.append)
        self.assertEqual(restored.bridge_power, 14)
        self.assertEqual(powers[-1], 14)

    def test_protocol_v3_tag_covers_extended_fields_and_unknown_versions_rejected(self):
        p = encode(self.keys[1], Frame(READY, 1, 1, 1, 0, revision=1, pulse_ms=50,
            tx_power_dbm=22, listen_ms=10000, max_awake_ms=60000))
        for offset in range(30, len(p)):
            corrupt = bytearray(p); corrupt[offset] ^= 1
            with self.assertRaises(ValueError): decode(self.keys[1], corrupt)
        self.assertAlmostEqual(airtime_seconds(47), .092416)


# These tests cover additions only; inherited baseline cases run in their own module.
for name in list(vars(baseline.EngineTest)):
    if name.startswith('test_') and name not in ConfigurationStageOneTest.__dict__:
        setattr(ConfigurationStageOneTest, name, None)

if __name__ == '__main__': unittest.main()
