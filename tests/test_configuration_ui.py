"""The generated view must reference real discovery IDs and preserve other views."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bridge/chacaico_lora_bridge'))
spec = importlib.util.spec_from_file_location('configuration_view', ROOT/'home-assistant/scripts/node-config-view.py')
view = importlib.util.module_from_spec(spec); spec.loader.exec_module(view)
spec = importlib.util.spec_from_file_location('discovery_under_test', ROOT/'bridge/chacaico_lora_bridge/bridge.py')
bridge = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'radio': types.SimpleNamespace(Radio=object),
        'paho': types.ModuleType('paho'), 'paho.mqtt': types.ModuleType('paho.mqtt'),
        'paho.mqtt.client': types.ModuleType('paho.mqtt.client')}):
    spec.loader.exec_module(bridge)

class ConfigurationUiTest(unittest.TestCase):
    def test_every_dashboard_entity_exists_and_ids_are_unique(self):
        discovery = list(bridge.bridge_discovery())
        for node in (1, 2, 3, 4): discovery += list(bridge.discovery(node))
        identifiers = [p['unique_id'] for _, p in discovery]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        entities = {p['default_entity_id'] for _, p in discovery if 'default_entity_id' in p}
        def walk(obj):
            if isinstance(obj, dict):
                if 'entity' in obj: self.assertIn(obj['entity'], entities)
                for v in obj.values(): walk(v)
            elif isinstance(obj, list):
                for v in obj: walk(v)
        walk(view.view())
        walk(view.advanced_view())
        json.dumps(discovery, allow_nan=False)

    def test_merge_preserves_user_main_view_and_is_idempotent(self):
        original = {'key': 'lovelace.dashboard_chacaico', 'data': {'config': {'views': [
            {'title': 'Mi campo', 'path': '0', 'cards': [{'type': 'entities', 'entities': ['switch.mi_valvula']}]},
            {'title': 'Otra vista', 'path': 'otra', 'cards': []}]}}}
        merged = view.merge(original)
        self.assertEqual(merged['data']['config']['views'][:2], original['data']['config']['views'])
        self.assertEqual(view.merge(merged), merged)
        self.assertEqual(len(original['data']['config']['views']), 2)

    def test_limits_match_protocol_and_commands_are_not_retained(self):
        from protocol import CONFIG_LIMITS
        for node in (1, 2, 3, 4):
            rows = dict(bridge.discovery(node))
            for key, (minimum, maximum) in CONFIG_LIMITS.items():
                row = rows[f'homeassistant/number/chacaico_node_{node}/{key}_requested/config']
                self.assertEqual(row['min'], minimum)
                pulse_max = 3000 if node in (1, 2) else 200
                self.assertEqual(row['max'], pulse_max if key == 'pulse_ms' else maximum)
                self.assertFalse(row['retain'])
                self.assertFalse(row['optimistic'])
        for topic, payload in list(rows.items()) + list(bridge.bridge_discovery()):
            if 'command_topic' in payload:
                self.assertFalse(payload['retain'])

if __name__ == '__main__': unittest.main()
