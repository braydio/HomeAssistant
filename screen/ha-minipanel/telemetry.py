"""Local-only procfs/sysfs stats and a bounded in-memory diagnostics ring. No psutil, no extra service."""
import os
import time
from collections import deque

COUNTERS = {k: 0 for k in ('ha_state_requests', 'ha_state_bytes', 'ha_actions', 'weather_forecasts',
                           'camera_requests', 'camera_bytes', 'network_errors', 'ui_long_frames')}
RING = deque(maxlen=200)  # (monotonic, event) - redacted: event names and counts only


def bump(name, n=1):
    COUNTERS[name] = COUNTERS.get(name, 0) + n


def note(event):
    RING.append((time.monotonic(), str(event)[:80]))


def _kv(path, key):
    try:
        with open(path, encoding='ascii', errors='ignore') as f:
            for line in f:
                if line.startswith(key):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def mem_available_kib(proc='/proc/meminfo'):
    return _kv(proc, 'MemAvailable:')


def rss_kib(proc='/proc/self/status'):
    return _kv(proc, 'VmRSS:')


def cpu_temp_c(path='/sys/class/thermal/thermal_zone0/temp'):
    try:
        with open(path, encoding='ascii') as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def ram_used_pct(proc='/proc/meminfo'):
    total, avail = _kv(proc, 'MemTotal:'), _kv(proc, 'MemAvailable:')
    return None if not total or avail is None else (total - avail) * 100.0 / total


def disk_used_pct(path='/'):
    try:
        st = os.statvfs(path)
        return (st.f_blocks - st.f_bavail) * 100.0 / st.f_blocks
    except (OSError, ZeroDivisionError):
        return None


def uptime_s(path='/proc/uptime'):
    try:
        with open(path, encoding='ascii') as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def mib(kib):
    return None if kib is None else round(kib / 1024)
