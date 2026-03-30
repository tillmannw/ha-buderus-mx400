"""Base entity for Buderus MX400."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MX400Coordinator


class MX400Entity(CoordinatorEntity[MX400Coordinator]):
    """Base class for MX400 entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MX400Coordinator,
        resource_path: str,
        name: str,
        gateway_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._resource_path = resource_path
        self._gateway_id = gateway_id
        slug = resource_path.strip("/").replace("/", "_").lower()
        self._attr_unique_id = f"mx400_{gateway_id}_{slug}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_id)},
            name=f"Buderus MX400 ({gateway_id})",
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=coordinator.firmware,
        )

    @property
    def _payload(self) -> dict | None:
        """Return the current payload from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._resource_path)

    @property
    def available(self) -> bool:
        return super().available and self._payload is not None
