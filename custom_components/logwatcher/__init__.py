"""Custom integration that exposes log health sensors.

The logwatcher integration provides sensors that count log entries at or
above a configured severity for a given log file. The logic for the
integration lives primarily in :mod:`custom_components.logwatcher.sensor`.
"""

from __future__ import annotations

# The platform is set up entirely within ``sensor.py``.
