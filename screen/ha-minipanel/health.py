"""Pi health summary from HA entities (Pi 4 via Glances/ping) and local stats (this Pi). Qt-free so it is unit-testable."""


def _num(state):
    try:
        return float(state)
    except (TypeError, ValueError):
        return None


def temp_c(st):
    """Temperature entity -> °C (HA reports °F or °C depending on the unit system)."""
    v = _num((st or {}).get('state'))
    if v is None:
        return None
    unit = ((st.get('attributes') or {}).get('unit_of_measurement') or '')
    return (v - 32) * 5 / 9 if unit.endswith('F') else v


def entity_ids(cfg):
    """Entity ids the panel must keep from the HA state poll."""
    return {cfg[k] for k in ('temp', 'ram', 'disk', 'ping') if cfg.get(k)}


def home_metrics(states, cfg):
    """Metrics of the HA host from configured entities; None where an entity is missing/unavailable."""
    if not any(cfg.get(k) for k in ('temp', 'ram', 'disk', 'ping')):
        return None
    ping = (states.get(cfg.get('ping')) or {}).get('state')
    return {'temp': temp_c(states.get(cfg.get('temp'))),
            'ram': _num((states.get(cfg.get('ram')) or {}).get('state')),
            'disk': _num((states.get(cfg.get('disk')) or {}).get('state')),
            'reachable': None if ping not in ('on', 'off') else ping == 'on'}


def problems(name, m, cfg):
    """Short warnings for one host's metrics; thresholds come from config (warn_temp_c / warn_disk_pct)."""
    out = []
    if not m:
        return out
    if m.get('reachable') is False:
        out.append(f'{name} unreachable')
    if m.get('temp') is not None and m['temp'] >= cfg['warn_temp_c']:
        out.append(f'{name} hot {m["temp"]:.0f} °C')
    if m.get('disk') is not None and m['disk'] >= cfg['warn_disk_pct']:
        out.append(f'{name} storage {m["disk"]:.0f}%')
    return out


def line(name, m):
    if m is None:
        return f'{name}: not configured'
    def f(v, fmt):
        return '?' if v is None else fmt % v
    return f'{name}: {f(m.get("temp"), "%.0f °C")} · RAM {f(m.get("ram"), "%.0f%%")} · storage {f(m.get("disk"), "%.0f%%")}'


def summarize(states, cfg, local):
    """-> (status line for the Home header, [detail lines for Settings], [problems])."""
    home = home_metrics(states, cfg)
    probs = problems('Pi 4', home, cfg) + problems('Screen', local, cfg)
    status = '▲ Check health' if probs else '● Healthy'
    lines = [line('Home (Pi 4)', home), line('Screen (this Pi)', local)]
    if probs:
        lines.append('Warning: ' + '; '.join(probs))
    return status, lines, probs
