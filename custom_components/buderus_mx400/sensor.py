"""Sensor platform for Buderus MX400 — auto-creates from all available resources."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GATEWAY_ID, DOMAIN
from .coordinator import MX400Coordinator
from .entity import MX400Entity

_LOGGER = logging.getLogger(__name__)

# Map PoinTT unitOfMeasure to HA device class / unit / state class
UNIT_MAP: dict[str, tuple[SensorDeviceClass | None, str | None, SensorStateClass | None]] = {
    "C_DEG": (SensorDeviceClass.TEMPERATURE, "\u00b0C", SensorStateClass.MEASUREMENT),
    "C": (SensorDeviceClass.TEMPERATURE, "\u00b0C", SensorStateClass.MEASUREMENT),
    "°C": (SensorDeviceClass.TEMPERATURE, "\u00b0C", SensorStateClass.MEASUREMENT),
    "F_DEG": (SensorDeviceClass.TEMPERATURE, "\u00b0F", SensorStateClass.MEASUREMENT),
    "K": (SensorDeviceClass.TEMPERATURE, "K", SensorStateClass.MEASUREMENT),
    "bar": (SensorDeviceClass.PRESSURE, "bar", SensorStateClass.MEASUREMENT),
    "%": (None, "%", SensorStateClass.MEASUREMENT),
    "l/min": (None, "L/min", SensorStateClass.MEASUREMENT),
    "kWh": (SensorDeviceClass.ENERGY, "kWh", SensorStateClass.TOTAL_INCREASING),
    "Wh": (SensorDeviceClass.ENERGY, "Wh", SensorStateClass.TOTAL_INCREASING),
    "W": (SensorDeviceClass.POWER, "W", SensorStateClass.MEASUREMENT),
    "kW": (SensorDeviceClass.POWER, "kW", SensorStateClass.MEASUREMENT),
    "mins": (SensorDeviceClass.DURATION, "min", SensorStateClass.MEASUREMENT),
    "min": (SensorDeviceClass.DURATION, "min", SensorStateClass.MEASUREMENT),
    "hours": (SensorDeviceClass.DURATION, "h", SensorStateClass.TOTAL_INCREASING),
    "h": (SensorDeviceClass.DURATION, "h", SensorStateClass.TOTAL_INCREASING),
}


def _make_name(path: str) -> str:
    """Generate a human-readable name from a resource path."""
    parts = path.strip("/").split("/")
    # For circuit paths like /heatingCircuits/hc1/roomTemperature -> HC1 Room Temperature
    name_parts: list[str] = []
    for p in parts:
        if p in ("heatingCircuits", "dhwCircuits", "solarCircuits", "heatSources",
                  "system", "gateway", "ventilation", "holidayMode", "recordings",
                  "sensors", "temperatures", "temperatureLevels", "resource"):
            continue
        # hc1 -> HC1, dhw1 -> DHW1
        if len(p) <= 4 and any(c.isdigit() for c in p):
            name_parts.append(p.upper())
        else:
            # camelCase to Title Case
            result = []
            for i, c in enumerate(p):
                if c.isupper() and i > 0 and p[i - 1].islower():
                    result.append(" ")
                result.append(c)
            name_parts.append("".join(result).replace("_", " ").title())
    return " ".join(name_parts) if name_parts else path


# Path patterns that should have a state class even without a unit
PATH_STATE_CLASS: dict[str, SensorStateClass] = {
    "numberOfStarts": SensorStateClass.TOTAL_INCREASING,
    "workingTime": SensorStateClass.TOTAL_INCREASING,
}


class MX400Sensor(MX400Entity, SensorEntity):
    """Dynamic sensor for any read-only MX400 resource."""

    def __init__(
        self,
        coordinator: MX400Coordinator,
        resource_path: str,
        gateway_id: str,
        payload: dict,
    ) -> None:
        name = _make_name(resource_path)
        super().__init__(coordinator, resource_path, name, gateway_id)

        unit = payload.get("unitOfMeasure")
        if unit and unit in UNIT_MAP:
            dc, native_unit, sc = UNIT_MAP[unit]
            self._attr_device_class = dc
            self._attr_native_unit_of_measurement = native_unit
            self._attr_state_class = sc
        elif unit:
            self._attr_native_unit_of_measurement = unit

        # Path-based state class fallback for counters without units
        if self._attr_state_class is None:
            for pattern, sc in PATH_STATE_CLASS.items():
                if pattern in resource_path:
                    self._attr_state_class = sc
                    break

    @property
    def native_value(self) -> Any:
        payload = self._payload
        if payload is None:
            return None
        value = payload.get("value")
        if isinstance(value, (dict, list)):
            return str(value)
        return value


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MX400Coordinator = hass.data[DOMAIN][entry.entry_id]
    gateway_id = entry.data[CONF_GATEWAY_ID]
    entities: list[MX400Sensor] = []

    for path, payload in coordinator.data.items():
        ptype = payload.get("type", "")
        writeable = payload.get("writeable", 0) == 1

        # Skip writable resources — those become number/select entities
        if writeable and ptype in ("floatValue", "integerValue", "stringValue"):
            if ptype == "stringValue" and payload.get("allowedValues"):
                continue  # -> select
            elif ptype in ("floatValue", "integerValue"):
                continue  # -> number

        # Skip complex types that don't map well to sensors
        if ptype in ("switchProgram", "arrayData", "configDataArray", "refEnum"):
            continue

        entities.append(MX400Sensor(coordinator, path, gateway_id, payload))

    _LOGGER.info("Creating %d sensor entities", len(entities))
    async_add_entities(entities)
