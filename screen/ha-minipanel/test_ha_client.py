"""Unit tests for the client; no Home Assistant server or GUI required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ha_client import HAClient, HomeAssistantError


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.c = HAClient({}, demo=True)

    def test_get_demo_states(self):
        self.assertTrue(any(s['entity_id'] == 'light.living_room' for s in self.c.states()))

    def test_switch_light(self):
        self.c.service('light','turn_off','light.living_room')
        found = next(s for s in self.c.states() if s['entity_id']=='light.living_room')
        self.assertEqual(found['state'],'off')

    def test_brightness(self):
        self.c.service('light','turn_on','light.living_room',brightness_pct=20)
        found = next(s for s in self.c.states() if s['entity_id']=='light.living_room')
        self.assertEqual(found['attributes']['brightness'],51)

    def test_no_unsupported_service(self):
        with self.assertRaises(ValueError):
            self.c.service('homeassistant','restart','homeassistant.core')

    def test_no_cross_domain_entities(self):
        with self.assertRaises(ValueError):
            self.c.service('light','turn_on','switch.some_device')

    def test_no_invalid_camera(self):
        with self.assertRaises(ValueError):
            self.c.camera_snapshot('light.living_room')

    def test_credentials_required(self):
        with patch.dict('os.environ', {'HA_TOKEN':''}):
            with self.assertRaises(HomeAssistantError):
                HAClient({'ha_url':'http://127.0.0.1:8123','token_file':'/path/to/missing/token'})


if __name__=='__main__': unittest.main()
