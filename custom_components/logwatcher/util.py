"""Utility helpers for the Log Watcher integration."""

from __future__ import annotations

import re

SEVERITY_ORDER = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def count_matching_lines(file_path: str, severity: str) -> int:
    """Count log lines matching the configured severity or higher."""

    severity = severity.upper()
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"Unsupported severity: {severity}")

    severity_index = SEVERITY_ORDER.index(severity)
    severities_to_match = "|".join(SEVERITY_ORDER[severity_index:])
    pattern = re.compile(r"\b(?:%s)\b" % severities_to_match)

    count = 0
    with open(file_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            if pattern.search(line):
                count += 1
    return count
