"""Small, dependency-free Home Assistant REST client. No browser required."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import telemetry
from colors import clamp_pct, clamp_rgb, clamp_kelvin


MAX_JSON_BYTES = 2 * 1024 * 1024


class HomeAssistantError(RuntimeError):
    pass


class HAClient:
    def __init__(self, config, demo=False):
        self.demo = demo
        self.demo_calls = []
        self.url = str(config.get('ha_url', '')).rstrip('/')
        self.config = config
        token_path = Path(os.path.expanduser(config.get('token_file', '~/.config/ha-minipanel/token')))
        self.token = os.environ.get('HA_TOKEN', '').strip()
        if not self.token and token_path.is_file():
            self.token = token_path.read_text(encoding='utf-8').strip()
        if not demo and (not self.url.startswith(('http://', 'https://')) or not self.token):
            raise HomeAssistantError('Set ha_url and create a token file (or set HA_TOKEN).')
        def L(eid, name, st, modes, **kw):
            return {'entity_id': eid, 'state': st, 'attributes': {'friendly_name': name, 'supported_color_modes': modes, **kw}}
        self._demo_states = [
            {'entity_id': 'sun.sun', 'state': 'below_horizon', 'attributes': {}},
            {'entity_id': 'weather.forecast_home', 'state': 'partlycloudy', 'attributes': {'temperature': 71, 'temperature_unit': '\u00b0F', 'humidity': 60, 'wind_speed': 6, 'wind_speed_unit': 'mph'}},
            L('light.kitchen_lights', 'Kitchen Lights', 'on', ['rgb'], brightness=180, entity_id=['light.kitchen_left', 'light.kitchen_right']),
            L('light.kitchen_left', 'Stove Left', 'on', ['rgb'], brightness=200, rgb_color=[255, 140, 0], min_color_temp_kelvin=2000, max_color_temp_kelvin=6500),
            L('light.kitchen_right', 'Stove Right', 'off', ['color_temp'], min_color_temp_kelvin=2200, max_color_temp_kelvin=5000),
            L('light.living_room_lights', 'Living Room', 'on', ['brightness'], brightness=120, entity_id=['light.living_room_lamp']),
            L('light.living_room_lamp', 'Floor Lamp', 'on', ['brightness'], brightness=120),
            L('light.bathroom_lights', 'Bathroom', 'off', ['onoff'], entity_id=['light.bathroom_vanity']),
            L('light.bathroom_vanity', 'Vanity', 'off', ['onoff']),
            L('light.bedroom_rope_lamp', 'Bedroom Rope Lamp', 'unavailable', []),
            L('light.office_office_main_light', 'Office Main', 'on', ['color_temp'], brightness=255, min_color_temp_kelvin=2700, max_color_temp_kelvin=6500),
            {'entity_id': 'scene.panel_relax', 'state': 'scening', 'attributes': {'friendly_name': 'Relax'}},
            {'entity_id': 'scene.panel_bright', 'state': 'scening', 'attributes': {'friendly_name': 'Bright'}},
            {'entity_id': 'scene.panel_night_lights', 'state': 'scening', 'attributes': {'friendly_name': 'Night'}},
            {'entity_id': 'input_select.home_panel_color_target', 'state': 'All', 'attributes': {'options': ['All', 'Kitchen', 'Living Room', 'Bathroom', 'Bedroom', 'Office']}},
        ]

    def request(self, method, path, payload=None, timeout=6):
        if self.demo:
            if method == 'GET' and path == '/api/states':
                return json.loads(json.dumps(self._demo_states))
            if method == 'POST' and path.startswith('/api/services/'):
                _, _, _, domain, service = path.split('/')
                eid = (payload or {}).get('entity_id', '')
                ids = eid if isinstance(eid, list) else eid.split(',')
                self.demo_calls.append((domain, service, list(ids), dict(payload or {})))
                for s in self._demo_states:
                    if s['entity_id'] in ids and domain == 'light':
                        s['state'] = 'off' if service == 'turn_off' else 'on'
                        if 'brightness_pct' in (payload or {}):
                            s['attributes']['brightness'] = round((payload['brightness_pct'] / 100) * 255)
                        if 'rgb_color' in (payload or {}):
                            s['attributes']['rgb_color'] = payload['rgb_color']
                    if s['entity_id'] in ids and domain == 'input_select':
                        s['state'] = payload['option']
                return []
            raise HomeAssistantError('Unsupported operation in demo mode')
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json'}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    raise HomeAssistantError('Response too large')
                if path == '/api/states':
                    telemetry.bump('ha_state_requests'); telemetry.bump('ha_state_bytes', len(raw))
                return json.loads(raw.decode('utf-8'))
        except (HTTPError, URLError, ValueError, TimeoutError, OSError) as e:
            telemetry.bump('network_errors')
            raise HomeAssistantError(f'Home Assistant request failed: {e}') from e

    def states(self, keep=None):
        """One GET /api/states, immediately reduced to the entities the panel uses.
        `keep(entity_id)->bool`; the full payload is dropped before returning."""
        out = self.request('GET', '/api/states')
        if not isinstance(out, list):
            raise HomeAssistantError('Unexpected states response')
        if keep is None:
            return out
        return [s for s in out if keep(s.get('entity_id', ''))]

    def service(self, domain, action, entity_ids, **data):
        """Allowlisted services only. Colour/brightness values are validated and clamped here."""
        colors = self.config.get('colors') or {}
        scripts = {v for k, v in colors.items() if k.endswith('_script') and v}
        helper = colors.get('target_entity')
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        entity_ids = list(dict.fromkeys(entity_ids or []))
        if (domain, action) not in {('light', 'turn_on'), ('light', 'turn_off'), ('scene', 'turn_on'),
                                    ('script', 'turn_on'), ('input_select', 'select_option')}:
            raise ValueError(f'Unsupported service: {domain}.{action}')
        if not entity_ids or len(entity_ids) > 40 or any(not isinstance(e, str) or not e.startswith(domain + '.') for e in entity_ids):
            raise ValueError('Entity IDs must match service domain')
        if domain == 'script' and not set(entity_ids) <= scripts:
            raise ValueError('Script is not allowlisted')
        if domain == 'input_select' and entity_ids != [helper]:
            raise ValueError('Helper is not allowlisted')
        if domain == 'light' and action == 'turn_on':
            clean = {}
            for k, v in data.items():
                if k == 'brightness_pct': clean[k] = clamp_pct(v)
                elif k == 'rgb_color': clean[k] = clamp_rgb(v)
                elif k == 'color_temp_kelvin': clean[k] = clamp_kelvin(v)
                else: raise ValueError(f'Unsupported light field: {k}')
            data = clean
        elif domain == 'script':
            variables = data.pop('variables', {})
            if data: raise ValueError('Unsupported script data')
            clean = {}
            for k, v in variables.items():
                if k == 'slot':
                    if int(v) not in (1, 2, 3, 4): raise ValueError('slot must be 1-4')
                    clean[k] = int(v)
                elif k == 'rgb': clean[k] = clamp_rgb(v)
                elif k == 'kelvin': clean[k] = clamp_kelvin(v)
                elif k == 'brightness': clean[k] = max(1, min(255, int(v)))
                else: raise ValueError(f'Unsupported script variable: {k}')
            data = {'variables': clean}
        elif domain == 'input_select':
            if set(data) != {'option'} or not isinstance(data['option'], str) or len(data['option']) > 40:
                raise ValueError('Bad option')
        elif data:
            raise ValueError('Unexpected service data')
        telemetry.bump('ha_actions')
        return self.request('POST', f'/api/services/{domain}/{action}', {'entity_id': entity_ids, **data})

    def forecast(self, entity_id, kind='daily'):
        """Daily/hourly forecast via weather.get_forecasts (returns a list of forecast dicts)."""
        if not entity_id.startswith('weather.'):
            raise ValueError('Not a weather entity')
        if self.demo:
            return []
        telemetry.bump('weather_forecasts')
        r = self.request('POST', '/api/services/weather/get_forecasts?return_response',
                         {'entity_id': entity_id, 'type': kind}, timeout=10)
        return ((r or {}).get('service_response') or {}).get(entity_id, {}).get('forecast', [])

    def camera_snapshot(self, entity_id, width=640, height=360):
        if not entity_id.startswith('camera.'):
            raise ValueError('Not a camera entity')
        if self.demo:
            return b''
        limit = int(self.config.get('camera_max_bytes', 1048576))
        limit = max(65536, min(limit, 3 * 1024 * 1024))
        path = f'/api/camera_proxy/{quote(entity_id, safe="._")}?width={int(width)}&height={int(height)}'
        req = Request(self.url + path, headers={'Authorization': f'Bearer {self.token}', 'Accept': 'image/*'})
        telemetry.bump('camera_requests')
        try:
            with urlopen(req, timeout=8) as response:
                if not response.headers.get('Content-Type', '').startswith('image/'):
                    raise HomeAssistantError('Camera proxy did not return an image')
                declared = response.headers.get('Content-Length')
                if declared and declared.isdigit() and int(declared) > limit:
                    raise HomeAssistantError('Snapshot too large')
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise HomeAssistantError('Snapshot too large')
                telemetry.bump('camera_bytes', len(data))
                return data
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            telemetry.bump('network_errors')
            raise HomeAssistantError(f'Camera unavailable: {e}') from e
