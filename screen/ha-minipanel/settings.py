"""Config validation/migration and default panel-room derivation. Qt-free so it is unit-testable."""
import re

_ID = re.compile(r'^[a-z_]+\.[a-z0-9_]+$')


class ConfigError(ValueError):
    pass


def slug(text):
    s = re.sub(r'[^a-z0-9]+', '_', str(text).lower()).strip('_')
    return (s or 'room')[:40]


def _eid(v, domain, what):
    if not isinstance(v, str) or not _ID.match(v) or not v.startswith(domain + '.'):
        raise ConfigError(f'{what}: invalid {domain} entity id')
    return v


def normalize(cfg):
    """Return a validated copy of cfg with defaults filled in. Old keys (lights/cameras) keep working."""
    c = dict(cfg)
    band = c.get('touch_band')
    if band is not None:
        if (not isinstance(band, (list, tuple)) or len(band) != 2 or not all(isinstance(x, int) for x in band)
                or not 0 <= band[0] < band[1]):
            raise ConfigError('touch_band must be [top, bottom] integers')
        c['touch_band'] = [int(band[0]), int(band[1])]
    c['poll_seconds'] = max(5, min(300, int(c.get('poll_seconds', 20))))
    c['snapshot_seconds'] = max(10, min(300, int(c.get('snapshot_seconds', 25))))
    c['diagnostics_seconds'] = max(10, min(300, int(c.get('diagnostics_seconds', 60))))
    c['camera_max_bytes'] = max(65536, min(3 * 1024 * 1024, int(c.get('camera_max_bytes', 1048576))))
    c['camera_max_decoded_pixels'] = max(10000, min(2073600, int(c.get('camera_max_decoded_pixels', 2073600))))
    c['camera_auto_refresh'] = bool(c.get('camera_auto_refresh', False))
    rooms, seen = [], set()
    for r in c.get('rooms') or []:
        if not isinstance(r, dict) or not r.get('label'):
            raise ConfigError('rooms entries need a label')
        eid = _eid(r.get('entity_id'), 'light', 'rooms')
        if eid in seen:
            raise ConfigError('duplicate room entity')
        seen.add(eid)
        pinned = [_eid(e, 'light', 'rooms.lights') for e in (r.get('lights') or [])]
        rooms.append({'label': str(r['label'])[:40], 'entity_id': eid, 'favorite': bool(r.get('favorite', True)), 'lights': pinned})
    c['rooms'] = rooms
    c['lights'] = [_eid(e, 'light', 'lights') for e in c.get('lights') or []]
    scenes = []
    for sc in c.get('scenes') or []:
        if isinstance(sc, str):
            scenes.append({'entity_id': _eid(sc, 'scene', 'scenes'), 'label': None})
        elif isinstance(sc, dict):
            scenes.append({'entity_id': _eid(sc.get('entity_id'), 'scene', 'scenes'), 'label': sc.get('label')})
        else:
            raise ConfigError('scenes entries must be ids or objects')
    c['scenes'] = scenes
    cams = list(c.get('camera_entities') or c.get('cameras') or [])
    c['camera_entities'] = [_eid(e, 'camera', 'cameras') for e in cams]
    colors = c.get('colors') or {}
    if colors:
        _eid(colors.get('target_entity'), 'input_select', 'colors')
        for k in ('apply_script', 'save_script', 'preset_script'):
            if colors.get(k):
                _eid(colors[k], 'script', 'colors')
    c['colors'] = colors
    if c.get('weather_entity'):
        _eid(c['weather_entity'], 'weather', 'weather_entity')
    return c


def is_group(state):
    return isinstance((state or {}).get('attributes', {}).get('entity_id'), list)


def members_of(states, eid, _depth=0):
    """Individual (non-group) light members of a light group; [eid] if it is not a resolvable group."""
    st = states.get(eid)
    ids = (st or {}).get('attributes', {}).get('entity_id')
    if not isinstance(ids, list):
        return [eid]
    out = []
    for m in ids:
        if not isinstance(m, str) or not m.startswith('light.'):
            continue
        if is_group(states.get(m)) and _depth < 2:
            out.extend(members_of(states, m, _depth + 1))
        else:
            out.append(m)
    return list(dict.fromkeys(out)) or [eid]


def default_rooms(cfg, states):
    """Curated defaults: configured rooms (or legacy `lights`), members from live HA groups, each light once."""
    cfg_rooms = cfg.get('rooms') or [
        {'label': ((states.get(e) or {}).get('attributes', {}).get('friendly_name') or e.split('.', 1)[1].replace('_', ' ').title()),
         'entity_id': e, 'favorite': True} for e in cfg.get('lights') or []]
    rooms, placed, used = [], set(), set()
    for r in cfg_rooms:
        rid = slug(r['label'])
        base = rid; n = 2
        while rid in used:
            rid = f'{base}_{n}'; n += 1
        used.add(rid)
        # `lights` pins members explicitly (useful while a group entity is unavailable and exposes no members)
        lights = [m for m in (r.get('lights') or members_of(states, r['entity_id'])) if m not in placed]
        placed.update(lights)
        rooms.append({'id': rid, 'label': r['label'], 'order': len(rooms), 'lights': lights,
                      'favorite': r.get('favorite', True), 'source': r['entity_id']})
    return rooms


def individual_light_ids(states):
    return {e for e, s in states.items() if e.startswith('light.') and not is_group(s)}
