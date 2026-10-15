"""Config normalisation, default rooms, state store, telemetry, client allowlist."""
import tempfile
import unittest
from pathlib import Path

import settings
import telemetry
from ha_client import HAClient
from state_store import StateStore, age_text


def st(eid, state='on', **attrs):
    return {'entity_id': eid, 'state': state, 'attributes': attrs}


class ConfigTests(unittest.TestCase):
    def test_old_keys_still_valid(self):
        c = settings.normalize({'lights': ['light.a'], 'cameras': ['camera.c'], 'scenes': ['scene.s']})
        self.assertEqual(c['camera_entities'], ['camera.c']); self.assertEqual(c['scenes'][0]['entity_id'], 'scene.s')

    def test_bad_values_rejected_without_secrets(self):
        for bad in ({'touch_band': [400, 100]}, {'touch_band': 'x'}, {'rooms': [{'label': 'A', 'entity_id': 'switch.x'}]},
                    {'rooms': [{'label': 'A', 'entity_id': 'light.a'}, {'label': 'B', 'entity_id': 'light.a'}]},
                    {'scenes': [5]}, {'colors': {'target_entity': 'light.x'}}):
            with self.assertRaises(settings.ConfigError): settings.normalize(bad)

    def test_ranges_clamped(self):
        c = settings.normalize({'poll_seconds': 1, 'camera_max_bytes': 10 ** 9})
        self.assertEqual(c['poll_seconds'], 5); self.assertEqual(c['camera_max_bytes'], 3 * 1024 * 1024)

    def test_touch_band_null_ok(self):
        self.assertIsNone(settings.normalize({'touch_band': None})['touch_band'])


class RoomTests(unittest.TestCase):
    def test_group_members_deduped_each_light_once(self):
        states = {s['entity_id']: s for s in [
            st('light.kitchen', entity_id=['light.a', 'light.b']), st('light.all', entity_id=['light.a', 'light.b', 'light.c']),
            st('light.a'), st('light.b'), st('light.c')]}
        cfg = settings.normalize({'rooms': [{'label': 'Kitchen', 'entity_id': 'light.kitchen'},
                                            {'label': 'Everything', 'entity_id': 'light.all'}]})
        rooms = settings.default_rooms(cfg, states)
        self.assertEqual(rooms[0]['lights'], ['light.a', 'light.b']); self.assertEqual(rooms[1]['lights'], ['light.c'])

    def test_unresolved_group_falls_back_to_itself(self):
        rooms = settings.default_rooms(settings.normalize({'rooms': [{'label': 'Den', 'entity_id': 'light.den'}]}), {'light.den': st('light.den', 'unavailable')})
        self.assertEqual(rooms[0]['lights'], ['light.den'])

    def test_pinned_lights_override_unresolved_group(self):
        cfg = settings.normalize({'rooms': [{'label': 'Living', 'entity_id': 'light.lr', 'lights': ['light.cat', 'light.over']}]})
        rooms = settings.default_rooms(cfg, {'light.lr': st('light.lr', 'unavailable')})
        self.assertEqual(rooms[0]['lights'], ['light.cat', 'light.over'])

    def test_group_not_counted_as_individual(self):
        states = {'light.g': st('light.g', entity_id=['light.a']), 'light.a': st('light.a')}
        self.assertEqual(settings.individual_light_ids(states), {'light.a'})


class StoreTests(unittest.TestCase):
    def test_diff_and_flags(self):
        s = StateStore(); self.assertIsNone(s.online)
        self.assertEqual(s.update([st('light.a'), st('light.b', 'off')], now=100.0), {'light.a', 'light.b'})
        self.assertEqual(s.generation, 1)
        self.assertEqual(s.update([st('light.a'), st('light.b', 'on')], now=110.0), {'light.b'})
        self.assertEqual(s.update([st('light.a'), st('light.b', 'on')], now=120.0), set()); self.assertEqual(s.generation, 2)
        s.failed(); self.assertFalse(s.online); self.assertEqual(s.last_success, 120.0)
        self.assertEqual(s.age(now=140.0), 20.0)

    def test_age_text(self):
        self.assertEqual(age_text(None), 'never'); self.assertEqual(age_text(30), '30s ago'); self.assertEqual(age_text(300), '5 min ago')


class TelemetryTests(unittest.TestCase):
    def test_missing_paths_are_none(self):
        self.assertIsNone(telemetry.cpu_temp_c('/nonexistent')); self.assertIsNone(telemetry.mem_available_kib('/nonexistent'))
        self.assertIsNone(telemetry.uptime_s('/nonexistent'))

    def test_parse(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, 'm'); p.write_text('MemTotal: 10 kB\nMemAvailable:   2048 kB\n')
            self.assertEqual(telemetry.mem_available_kib(str(p)), 2048)
            t = Path(d, 't'); t.write_text('41234\n'); self.assertAlmostEqual(telemetry.cpu_temp_c(str(t)), 41.234)

    def test_ring_bounded(self):
        for i in range(500): telemetry.note(i)
        self.assertEqual(len(telemetry.RING), 200)


class AllowlistTests(unittest.TestCase):
    def setUp(self):
        self.c = HAClient(settings.normalize({'colors': {
            'target_entity': 'input_select.t', 'apply_script': 'script.apply', 'save_script': 'script.save', 'preset_script': 'script.preset'}}), demo=True)

    def test_light_fields_clamped_and_unknown_rejected(self):
        self.c.service('light', 'turn_on', ['light.a', 'light.a'], rgb_color=[999, 0, 0], brightness_pct=500)
        d, s, ids, payload = self.c.demo_calls[-1]
        self.assertEqual(ids, ['light.a']); self.assertEqual(payload['rgb_color'], [255, 0, 0]); self.assertEqual(payload['brightness_pct'], 100)
        with self.assertRaises(ValueError): self.c.service('light', 'turn_on', 'light.a', effect='x')

    def test_scripts_only_if_allowlisted(self):
        self.c.service('script', 'turn_on', 'script.preset', variables={'slot': 2})
        with self.assertRaises(ValueError): self.c.service('script', 'turn_on', 'script.other', variables={})
        with self.assertRaises(ValueError): self.c.service('script', 'turn_on', 'script.preset', variables={'slot': 9})
        with self.assertRaises(ValueError): self.c.service('script', 'turn_on', 'script.preset', variables={'evil': 1})

    def test_helper_only_the_configured_one(self):
        self.c.service('input_select', 'select_option', 'input_select.t', option='Kitchen')
        with self.assertRaises(ValueError): self.c.service('input_select', 'select_option', 'input_select.u', option='x')

    def test_no_generic_services(self):
        for d, a, e in (('homeassistant', 'restart', 'homeassistant.x'), ('light', 'toggle', 'light.a'), ('switch', 'turn_on', 'switch.a')):
            with self.assertRaises(ValueError): self.c.service(d, a, e)

    def test_states_filter_drops_rest(self):
        self.assertTrue(all(s['entity_id'].startswith('light.') for s in self.c.states(lambda e: e.startswith('light.'))))


if __name__ == '__main__': unittest.main()
