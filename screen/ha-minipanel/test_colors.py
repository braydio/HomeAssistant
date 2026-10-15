import unittest

import colors as C


def light(state, modes, **attrs):
    return {'entity_id': 'light.x', 'state': state, 'attributes': {'supported_color_modes': modes, **attrs}}


class ColorTests(unittest.TestCase):
    def test_onoff_only(self):
        cap = C.capabilities(light('on', ['onoff']))
        self.assertFalse(cap['colorable']); self.assertFalse(cap['dimmer']); self.assertIn('On/off only', cap['reason'])
        self.assertIsNone(C.build_payload(light('on', ['onoff']), ('rgb', [1, 2, 3])))

    def test_dimmer_only(self):
        s = light('on', ['brightness'])
        cap = C.capabilities(s)
        self.assertTrue(cap['dimmer']); self.assertFalse(cap['colorable']); self.assertIn('Brightness only', cap['reason'])

    def test_color_temp_only(self):
        s = light('on', ['color_temp'], min_color_temp_kelvin=2700, max_color_temp_kelvin=6500)
        self.assertTrue(C.capabilities(s)['temp']); self.assertFalse(C.capabilities(s)['rgb'])
        self.assertIsNone(C.build_payload(s, ('rgb', [255, 0, 0])))
        self.assertEqual(C.build_payload(s, ('temp', 2000))['color_temp_kelvin'], 2700)   # clamped to device range
        self.assertEqual(C.build_payload(s, ('temp', 9000))['color_temp_kelvin'], 6500)

    def test_rgb_modes_and_clamp(self):
        for m in ('hs', 'xy', 'rgb', 'rgbw', 'rgbww'):
            self.assertTrue(C.capabilities(light('on', [m]))['rgb'], m)
        s = light('on', ['rgb'])
        self.assertEqual(C.build_payload(s, ('rgb', [300, -5, 12]))['rgb_color'], [255, 0, 12])

    def test_unreachable(self):
        s = light('unavailable', ['rgb'])
        self.assertFalse(C.capabilities(s)['available']); self.assertIsNone(C.build_payload(s, ('rgb', [1, 1, 1])))
        self.assertIn('unavailable', C.capabilities(s)['reason'])

    def test_brightness_only_included_when_supported(self):
        self.assertEqual(C.build_payload(light('on', ['rgb']), ('rgb', [1, 2, 3]), 150)['brightness_pct'], 100)
        self.assertNotIn('brightness_pct', C.build_payload(light('on', ['rgb']), ('rgb', [1, 2, 3])))
        self.assertNotIn('brightness_pct', C.build_payload(light('on', ['onoff', 'color_temp'][:1] + ['rgb']) , ('rgb', [1, 2, 3]), None))

    def test_mixed_group_eligibility(self):
        states = {'light.a': light('on', ['rgb']), 'light.b': light('on', ['color_temp']),
                  'light.c': light('on', ['onoff']), 'light.d': light('unavailable', ['rgb'])}
        ok, skipped = C.eligible(states, ['light.a', 'light.b', 'light.c', 'light.d'], ('rgb', [255, 0, 0]))
        self.assertEqual((ok, skipped), (['light.a'], ['light.b', 'light.c', 'light.d']))
        ok, _ = C.eligible(states, list(states), ('temp', 2700))
        self.assertEqual(ok, ['light.b'])

    def test_bad_rgb_shape(self):
        with self.assertRaises(ValueError): C.clamp_rgb([1, 2])


if __name__ == '__main__': unittest.main()
