"""Small, dependency-free Home Assistant REST client. No browser required."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class HomeAssistantError(RuntimeError):
    pass


class HAClient:
    def __init__(self, config, demo=False):
        self.demo = demo
        self.url = str(config.get('ha_url', '')).rstrip('/')
        self.config = config
        token_path = Path(os.path.expanduser(config.get('token_file', '~/.config/ha-minipanel/token')))
        self.token = os.environ.get('HA_TOKEN', '').strip()
        if not self.token and token_path.is_file():
            self.token = token_path.read_text(encoding='utf-8').strip()
        if not demo and (not self.url.startswith(('http://', 'https://')) or not self.token):
            raise HomeAssistantError('Set ha_url and create a token file (or set HA_TOKEN).')
        self._demo_states = [
            {'entity_id':'sun.sun', 'state':'below_horizon','attributes':{}},
            {'entity_id':'light.living_room','state':'on','attributes':{'friendly_name':'Living Room','brightness':177,'supported_color_modes':['brightness']}},
            {'entity_id':'light.bedroom','state':'on','attributes':{'friendly_name':'Bedroom','brightness':103,'supported_color_modes':['color_temp']}},
            {'entity_id':'light.porch','state':'off','attributes':{'friendly_name':'Porch','supported_color_modes':['onoff']}},
            {'entity_id':'scene.relax','state':'scening','attributes':{'friendly_name':'Relax'}},
            {'entity_id':'scene.bright','state':'scening','attributes':{'friendly_name':'Bright'}},
            {'entity_id':'scene.night','state':'scening','attributes':{'friendly_name':'Night'}},
            {'entity_id':'camera.tapo_c120','state':'idle','attributes':{'friendly_name':'Tapo C120'}},
        ]

    def request(self, method, path, payload=None, timeout=6):
        if self.demo:
            if method == 'GET' and path == '/api/states':
                return json.loads(json.dumps(self._demo_states))
            if method == 'POST' and path.startswith('/api/services/'):
                _, _, _, domain, service = path.split('/')
                eid = (payload or {}).get('entity_id', '')
                ids = eid if isinstance(eid, list) else eid.split(',')
                for s in self._demo_states:
                    if s['entity_id'] in ids and domain == 'light':
                        s['state'] = 'off' if service == 'turn_off' else 'on'
                        if 'brightness_pct' in (payload or {}):
                            s['attributes']['brightness'] = round((payload['brightness_pct'] / 100) * 255)
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
                return json.loads(response.read().decode('utf-8'))
        except (HTTPError, URLError, ValueError, TimeoutError) as e:
            raise HomeAssistantError(f'Home Assistant request failed: {e}') from e

    def states(self):
        return self.request('GET', '/api/states')

    def service(self, domain, action, entity_ids, **data):
        allowed = {'light': {'turn_on','turn_off'},
                   'scene': {'turn_on'}, 'script': {'turn_on'}}
        if action not in allowed.get(domain, set()):
            raise ValueError(f'Unsupported service: {domain}.{action}')
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        if not entity_ids or any(not eid.startswith(domain + '.') for eid in entity_ids):
            raise ValueError('Entity IDs must match service domain')
        return self.request('POST', f'/api/services/{domain}/{action}',
                            {'entity_id': entity_ids, **data})

    def camera_snapshot(self, entity_id, width=720, height=400):
        if not entity_id.startswith('camera.'):
            raise ValueError('Not a camera entity')
        if self.demo:
            return b''
        path = f'/api/camera_proxy/{quote(entity_id, safe="._")}?width={int(width)}&height={int(height)}'
        req = Request(self.url + path, headers={'Authorization':f'Bearer {self.token}', 'Accept':'image/*'})
        try:
            with urlopen(req, timeout=8) as response:
                if not response.headers.get('Content-Type', '').startswith('image/'):
                    raise HomeAssistantError('Camera proxy did not return an image')
                data = response.read(3 * 1024 * 1024 + 1)
                if len(data) > 3 * 1024 * 1024:
                    raise HomeAssistantError('Snapshot larger than 3 MB')
                return data
        except (HTTPError, URLError, TimeoutError) as e:
            raise HomeAssistantError(f'Camera unavailable: {e}') from e
