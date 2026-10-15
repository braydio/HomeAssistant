"""Pure (Qt-free) colour capability + validation helpers for individual lights."""

RGB_MODES = frozenset({'hs', 'xy', 'rgb', 'rgbw', 'rgbww'})
SWATCHES = (('Red', (255, 0, 0)), ('Orange', (255, 140, 0)), ('Green', (0, 200, 60)),
            ('Cyan', (0, 220, 220)), ('Blue', (30, 80, 255)), ('Purple', (150, 60, 255)),
            ('Pink', (255, 80, 170)))
TEMPS = (('Warm White', 2700), ('Daylight', 4000))
DEFAULT_KELVIN = (2000, 6500)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def capabilities(state):
    """What can this light do, from live HA attributes. Never assumes a mode."""
    state = state or {}
    attrs = state.get('attributes') or {}
    st = state.get('state')
    modes = set(attrs.get('supported_color_modes') or [])
    available = st not in (None, 'unavailable', 'unknown')
    rgb = bool(modes & RGB_MODES)
    temp = 'color_temp' in modes
    dimmer = bool(modes - {'onoff', 'unknown'}) or ('brightness' in attrs and not modes)
    kmin = attrs.get('min_color_temp_kelvin') or DEFAULT_KELVIN[0]
    kmax = attrs.get('max_color_temp_kelvin') or DEFAULT_KELVIN[1]
    try:
        kmin, kmax = int(kmin), int(kmax)
    except (TypeError, ValueError):
        kmin, kmax = DEFAULT_KELVIN
    if kmin >= kmax:
        kmin, kmax = DEFAULT_KELVIN
    if not available:
        reason = 'Light is unavailable right now.'
    elif not (rgb or temp):
        reason = 'Brightness only - this light has no colour.' if dimmer else 'On/off only - this light has no colour.'
    else:
        reason = ''
    return {'available': available, 'rgb': rgb, 'temp': temp, 'dimmer': dimmer,
            'kmin': kmin, 'kmax': kmax, 'colorable': available and (rgb or temp), 'reason': reason}


def clamp_rgb(rgb):
    if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
        raise ValueError('rgb must have 3 values')
    return [int(clamp(int(c), 0, 255)) for c in rgb]


def clamp_kelvin(k, kmin=DEFAULT_KELVIN[0], kmax=DEFAULT_KELVIN[1]):
    return int(clamp(int(k), max(2000, int(kmin)), min(6500, int(kmax))))


def clamp_pct(p):
    return int(clamp(int(p), 1, 100))


def build_payload(state, choice, brightness_pct=None):
    """choice is ('rgb',[r,g,b]) or ('temp',kelvin). Returns light.turn_on data for ONE light, or None
    when the light cannot do it (caller shows the reason)."""
    cap = capabilities(state)
    if not cap['available']:
        return None
    kind, value = choice
    data = {}
    if kind == 'rgb':
        if not cap['rgb']:
            return None
        data['rgb_color'] = clamp_rgb(value)
    elif kind == 'temp':
        if not cap['temp']:
            return None
        data['color_temp_kelvin'] = clamp_kelvin(value, cap['kmin'], cap['kmax'])
    else:
        raise ValueError('unknown colour kind')
    if brightness_pct is not None and cap['dimmer']:
        data['brightness_pct'] = clamp_pct(brightness_pct)
    return data


def eligible(states_by_id, ids, choice):
    """Split ids into (eligible, skipped) for a colour choice; skips unsupported/unavailable lights."""
    ok, skipped = [], []
    for eid in ids:
        (ok if build_payload(states_by_id.get(eid), choice) is not None else skipped).append(eid)
    return ok, skipped
