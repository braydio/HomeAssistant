"""Unit tests for the Log Watcher integration."""

# ruff: noqa: E402

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from custom_components.logwatcher.util import count_matching_lines


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    """Create a temporary log file for tests."""

    log_contents = """
    2024-05-12 09:00:00 INFO Starting Home Assistant
    2024-05-12 09:01:00 WARNING Integration slow to start
    2024-05-12 09:02:00 ERROR Failed to connect
    2024-05-12 09:03:00 CRITICAL System failure imminent
    """.strip()
    file_path = tmp_path / "home-assistant.log"
    file_path.write_text(log_contents, encoding="utf-8")
    return file_path


def test_count_matching_lines_respects_severity(log_file: Path) -> None:
    """The helper should respect severity thresholds."""

    assert count_matching_lines(str(log_file), "WARNING") == 3
    assert count_matching_lines(str(log_file), "ERROR") == 2
    assert count_matching_lines(str(log_file), "CRITICAL") == 1


def test_count_matching_lines_rejects_invalid_severity(log_file: Path) -> None:
    """Invalid severity levels should raise a :class:`ValueError`."""

    with pytest.raises(ValueError):
        count_matching_lines(str(log_file), "ALERT")
