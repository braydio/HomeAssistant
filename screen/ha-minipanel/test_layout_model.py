import json
import os
import tempfile
import unittest
from pathlib import Path

from layout_model import PanelLayout, LayoutError, validate_data

DEFAULTS = {'version': 1, 'rooms': [
    {'id': 'kitchen', 'label': 'Kitchen', 'order': 0, 'lights': ['light.k_left', 'light.k_right']},
    {'id': 'office', 'label': 'Office', 'order': 1, 'lights': ['light.office']},
    {'id': 'bath', 'label': 'Bath', 'order': 2, 'lights': []}]}
ALLOWED = {'light.k_left', 'light.k_right', 'light.office', 'light.extra'}


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / 'cfg' / 'layout.json'
        self.lay = PanelLayout.load(self.path, DEFAULTS, ALLOWED)

    def test_defaults_when_missing(self):
        self.assertFalse(self.lay.loaded_from_file)
        self.assertEqual(self.lay.room('kitchen')['lights'], ['light.k_left', 'light.k_right'])

    def test_move_between_rooms_and_each_light_once(self):
        self.lay.move_light('light.k_right', 'office')
        self.assertEqual(self.lay.room_of('light.k_right'), 'office')
        self.assertEqual(self.lay.all_lights().count('light.k_right'), 1)
        self.lay.move_light('light.k_left', 'office', before_id='light.office')
        self.assertEqual(self.lay.room('office')['lights'][0], 'light.k_left')
        self.lay.validate()

    def test_reorder_light_and_room_clamped(self):
        self.lay.reorder_light('kitchen', 'light.k_right', 0)
        self.assertEqual(self.lay.room('kitchen')['lights'][0], 'light.k_right')
        self.lay.reorder_light('kitchen', 'light.k_right', 99)
        self.assertEqual(self.lay.room('kitchen')['lights'][-1], 'light.k_right')
        self.lay.reorder_room('bath', 0)
        self.assertEqual([r['id'] for r in self.lay.rooms()], ['bath', 'kitchen', 'office'])
        self.assertEqual([r['order'] for r in self.lay.rooms()], [0, 1, 2])

    def test_unknown_light_or_room_rejected(self):
        with self.assertRaises(LayoutError): self.lay.move_light('light.nope', 'office')
        with self.assertRaises(LayoutError): self.lay.move_light('light.k_left', 'nope')

    def test_cancel_discards_and_nothing_persisted(self):
        self.lay.move_light('light.k_left', 'office')
        self.assertTrue(self.lay.dirty)
        self.lay.cancel()
        self.assertFalse(self.lay.dirty)
        self.assertEqual(self.lay.room_of('light.k_left'), 'kitchen')
        self.assertFalse(self.path.exists())

    def test_commit_persists_with_modes_and_reload(self):
        self.lay.move_light('light.k_left', 'office'); self.lay.reorder_room('office', 0)
        self.lay.commit_atomic()
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), '0o600')
        self.assertEqual(oct(self.path.parent.stat().st_mode & 0o777), '0o700')
        again = PanelLayout.load(self.path, DEFAULTS, ALLOWED)
        self.assertTrue(again.loaded_from_file)
        self.assertEqual(again.rooms()[0]['id'], 'office')
        self.assertEqual(again.room_of('light.k_left'), 'office')

    def test_second_commit_keeps_backup(self):
        self.lay.commit_atomic(); self.lay.move_light('light.k_left', 'office'); self.lay.commit_atomic()
        bak = self.path.with_name('layout.json.bak')
        self.assertTrue(bak.exists())
        self.assertEqual(json.loads(bak.read_text())['rooms'][0]['lights'][0], 'light.k_left')

    def test_malformed_falls_back_to_backup_then_defaults(self):
        self.lay.commit_atomic(); self.lay.move_light('light.k_left', 'office'); self.lay.commit_atomic()
        self.path.write_text('{not json')
        rec = PanelLayout.load(self.path, DEFAULTS, ALLOWED)   # recovers from .bak (the first commit)
        self.assertEqual(rec.room_of('light.k_left'), 'kitchen')
        self.path.with_name('layout.json.bak').write_text('garbage')
        dflt = PanelLayout.load(self.path, DEFAULTS, ALLOWED)
        self.assertFalse(dflt.loaded_from_file)

    def test_duplicate_membership_and_bad_schema_rejected(self):
        bad = json.loads(json.dumps(DEFAULTS)); bad['rooms'][1]['lights'].append('light.k_left')
        with self.assertRaises(LayoutError): validate_data(bad)
        with self.assertRaises(LayoutError): validate_data({'version': 2, 'rooms': []})
        bad2 = json.loads(json.dumps(DEFAULTS)); bad2['rooms'][0]['lights'] = ['switch.x']
        with self.assertRaises(LayoutError): validate_data(bad2)
        bad3 = json.loads(json.dumps(DEFAULTS)); bad3['rooms'][1]['id'] = 'kitchen'
        with self.assertRaises(LayoutError): validate_data(bad3)

    def test_unknown_ids_pruned_on_load_but_unavailable_kept(self):
        self.lay.move_light('light.office', 'kitchen'); self.lay.commit_atomic()
        pr = PanelLayout.load(self.path, DEFAULTS, {'light.k_left', 'light.k_right'})
        self.assertNotIn('light.office', pr.all_lights())

    def test_reset_to_defaults(self):
        self.lay.move_light('light.k_left', 'office'); self.lay.reset_to_defaults()
        self.assertEqual(self.lay.room_of('light.k_left'), 'kitchen')

    def test_fifty_rearrangements_stay_valid(self):
        ids = ['kitchen', 'office', 'bath']
        for i in range(50):
            self.lay.move_light('light.k_left' if i % 2 else 'light.office', ids[i % 3]); self.lay.reorder_room(ids[(i + 1) % 3], i % 3)
        self.lay.validate(); self.assertEqual(len(self.lay.all_lights()), 3)


if __name__ == '__main__': unittest.main()
