"""Number platform for Buderus MX400 — auto-creates from writable numeric resources."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GATEWAY_ID, DOMAIN
from .coordinator import MX400Coordinator
from .entity import MX400Entity
from .sensor import _make_name

_LOGGER = logging.getLogger(__name__)

UNIT_TO_DEVICE_CLASS: dict[str, NumberDeviceClass] = {
    "C_DEG": NumberDeviceClass.TEMPERATURE,
    "F_DEG": NumberDeviceClass.TEMPERATURE,
}

UNIT_TO_NATIVE: dict[str, str] = {
    "C_DEG": "\u00b0C",
    "F_DEG": "\u00b0F",
    "bar": "bar",
    "%": "%",
    "l/min": "L/min",
    "kWh": "kWh",
    "W": "W",
    "mins": "min",
    "hours": "h",
}


class MX400Number(MX400Entity, NumberEntity):
    """Writable number entity for any numeric MX400 resource."""

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
        if unit:
            self._attr_device_class = UNIT_TO_DEVICE_CLASS.get(unit)
            self._attr_native_unit_of_measurement = UNIT_TO_NATIVE.get(unit, unit)

        if "minValue" in payload:
            self._attr_native_min_value = float(payload["minValue"])
        if "maxValue" in payload:
            self._attr_native_max_value = float(payload["maxValue"])
        if "stepSize" in payload:
            self._attr_native_step = float(payload["stepSize"])

    @property
    def native_value(self) -> float | None:
        payload = self._payload
        if payload is None:
            return None
        value = payload.get("value")
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        # Use int if the resource is integerValue
        payload = self._payload
        if payload and payload.get("type") == "integerValue":
            write_value = int(value)
        else:
            write_value = value

        success = await self.hass.async_add_executor_job(
            self.coordinator.client.write, self._resource_path, write_value
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set %s to %s", self._resource_path, value)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MX400Coordinator = hass.data[DOMAIN][entry.entry_id]
    gateway_id = entry.data[CONF_GATEWAY_ID]
    entities: list[MX400Number] = []

    for path, payload in coordinator.data.items():
        ptype = payload.get("type", "")
        writeable = payload.get("writeable", 0) == 1

        if writeable and ptype in ("floatValue", "integerValue"):
            entities.append(MX400Number(coordinator, path, gateway_id, payload))

    _LOGGER.info("Creating %d number entities", len(entities))
    async_add_entities(entities)
