"""Health summary: unit conversion, thresholds, missing data."""
import unittest

import tempfile
from pathlib import Path

import health
import settings
import telemetry

CFG = settings.normalize({'health': {'temp': 'sensor.t', 'ram': 'sensor.r', 'disk': 'sensor.d', 'ping': 'binary_sensor.p'}})['health']


def st(eid, state, unit=None):
    return {'entity_id': eid, 'state': state, 'attributes': {'unit_of_measurement': unit} if unit else {}}


def states(temp='120.2', unit='°F', ram='35', disk='13', ping='on'):
    return {e['entity_id']: e for e in (st('sensor.t', temp, unit), st('sensor.r', ram, '%'),
                                         st('sensor.d', disk, '%'), st('binary_sensor.p', ping))}


class HealthTests(unittest.TestCase):
    def test_fahrenheit_converted(self):
        self.assertAlmostEqual(health.temp_c(st('x', '120.2', '°F')), 49.0, 1)
        self.assertEqual(health.temp_c(st('x', '49', '°C')), 49.0)
        self.assertIsNone(health.temp_c(st('x', 'unavailable', '°C')))

    def test_healthy(self):
        status, lines, probs = health.summarize(states(), CFG, {'temp': 42.0, 'ram': 45, 'disk': 22})
        self.assertEqual(status, '● Healthy'); self.assertEqual(probs, [])
        self.assertIn('49 °C', lines[0]); self.assertIn('42 °C', lines[1])

    def test_warnings(self):
        _, lines, probs = health.summarize(states(temp='176', disk='90', ping='off'), CFG, {'temp': 80.0, 'ram': 90, 'disk': 30})
        self.assertEqual(len(probs), 4); self.assertTrue(lines[-1].startswith('Warning: '))
        self.assertEqual(health.summarize(states(disk='90'), CFG, {})[0], '▲ Check health')

    def test_missing_data_is_not_a_warning(self):
        status, lines, probs = health.summarize({}, CFG, {'temp': None, 'ram': None, 'disk': None})
        self.assertEqual(probs, []); self.assertIn('?', lines[0])

    def test_unconfigured(self):
        cfg = settings.normalize({})['health']
        status, lines, _ = health.summarize({}, cfg, {})
        self.assertEqual(status, '● Healthy'); self.assertIn('not configured', lines[0])
        self.assertEqual(health.entity_ids(cfg), set())

    def test_config_validation(self):
        for bad in ({'temp': 'light.x'}, {'ping': 'sensor.p'}, {'disk': 'bad id'}):
            with self.assertRaises(settings.ConfigError): settings.normalize({'health': bad})
        c = settings.normalize({'health': {'warn_temp_c': 5, 'warn_disk_pct': 500}})['health']
        self.assertEqual((c['warn_temp_c'], c['warn_disk_pct']), (40, 99))

    def test_local_stats(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'meminfo'; p.write_text('MemTotal: 400000 kB\nMemAvailable: 100000 kB\n')
            self.assertEqual(telemetry.ram_used_pct(str(p)), 75.0)
            self.assertIsNone(telemetry.ram_used_pct(str(Path(d) / 'missing')))
        self.assertTrue(0 <= telemetry.disk_used_pct('/') <= 100)
        self.assertIsNone(telemetry.disk_used_pct('/nonexistent-path'))


if __name__ == '__main__':
    unittest.main()
