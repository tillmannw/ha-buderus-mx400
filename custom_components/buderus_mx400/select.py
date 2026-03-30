"""Select platform for Buderus MX400 — auto-creates from writable string resources with allowedValues."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GATEWAY_ID, DOMAIN
from .coordinator import MX400Coordinator
from .entity import MX400Entity
from .sensor import _make_name

_LOGGER = logging.getLogger(__name__)


class MX400Select(MX400Entity, SelectEntity):
    """Select entity for writable string resources with allowedValues."""

    def __init__(
        self,
        coordinator: MX400Coordinator,
        resource_path: str,
        gateway_id: str,
        payload: dict,
    ) -> None:
        name = _make_name(resource_path)
        super().__init__(coordinator, resource_path, name, gateway_id)
        self._attr_options = payload.get("allowedValues", [])

    @property
    def current_option(self) -> str | None:
        payload = self._payload
        if payload is None:
            return None
        return str(payload.get("value"))

    async def async_select_option(self, option: str) -> None:
        success = await self.hass.async_add_executor_job(
            self.coordinator.client.write, self._resource_path, option
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set %s to %s", self._resource_path, option)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MX400Coordinator = hass.data[DOMAIN][entry.entry_id]
    gateway_id = entry.data[CONF_GATEWAY_ID]
    entities: list[MX400Select] = []

    for path, payload in coordinator.data.items():
        ptype = payload.get("type", "")
        writeable = payload.get("writeable", 0) == 1

        if writeable and ptype == "stringValue" and payload.get("allowedValues"):
            entities.append(MX400Select(coordinator, path, gateway_id, payload))

    _LOGGER.info("Creating %d select entities", len(entities))
    async_add_entities(entities)
