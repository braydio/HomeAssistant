"""Sensor platform for the Log Watcher integration.

This module defines the :class:`LogWatcherSensor` entity which counts the
number of log lines at or above a configured severity in a given log file.
The entity relies on a :class:`~homeassistant.helpers.update_coordinator.DataUpdateCoordinator`
for efficient polling and file parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import CONF_FILE_PATH, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
import voluptuous as vol

from .util import SEVERITY_ORDER, count_matching_lines

_LOGGER = logging.getLogger(__name__)

CONF_SEVERITY = "severity"
DEFAULT_NAME = "Log Watcher"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
DEFAULT_SEVERITY = "WARNING"

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_FILE_PATH): cv.path,
        vol.Optional(CONF_SEVERITY, default=DEFAULT_SEVERITY): vol.In(SEVERITY_ORDER),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            cv.time_period, cv.positive_timedelta
        ),
    }
)


@dataclass(frozen=True)
class LogWatcherEntityDescription(SensorEntityDescription):
    """Metadata describing a Log Watcher sensor."""

    severity: str
    file_path: str


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Log Watcher sensor platform from YAML."""

    del discovery_info

    name = config[CONF_NAME]
    severity = config[CONF_SEVERITY]
    file_path = hass.config.path(config[CONF_FILE_PATH])
    scan_interval: timedelta = config[CONF_SCAN_INTERVAL]

    coordinator = DataUpdateCoordinator[int](
        hass,
        _LOGGER,
        name=f"logwatcher_{name}",
        update_method=_build_update_method(hass, file_path, severity),
        update_interval=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    description = LogWatcherEntityDescription(
        key="logwatcher_count",
        name=name,
        native_unit_of_measurement="entries",
        severity=severity,
        file_path=file_path,
    )

    async_add_entities(
        [LogWatcherSensor(description=description, coordinator=coordinator)],
        True,
    )


def _build_update_method(
    hass: HomeAssistant, file_path: str, severity: str
) -> Callable[[], int]:
    """Create the update method for the coordinator."""

    def _update() -> int:
        try:
            return count_matching_lines(file_path, severity)
        except FileNotFoundError:
            _LOGGER.warning("Log file %s was not found", file_path)
            return 0

    async def _async_update() -> int:
        return await hass.async_add_executor_job(_update)

    return _async_update


class LogWatcherSensor(CoordinatorEntity[DataUpdateCoordinator[int]], SensorEntity):
    """Representation of the log watcher sensor."""

    entity_description: LogWatcherEntityDescription

    def __init__(
        self,
        *,
        description: LogWatcherEntityDescription,
        coordinator: DataUpdateCoordinator[int],
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self.entity_description = description
        self._attr_native_value = coordinator.data
        self._attr_name = description.name
        self._attr_unique_id = f"logwatcher_{description.file_path}_{description.severity}"

    @property
    def native_value(self) -> int:
        """Return the number of matching log entries."""

        return int(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose additional metadata about the monitored log."""

        return {
            "file_path": self.entity_description.file_path,
            "severity": self.entity_description.severity,
        }
