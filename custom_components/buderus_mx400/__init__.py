"""Buderus MX400 integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import PointtClient, TokenManager
from .const import (
    CONF_CLIENT_ID,
    CONF_GATEWAY_ID,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    DEFAULT_CLIENT_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import MX400Coordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Buderus MX400 from a config entry."""
    gateway_id = entry.data[CONF_GATEWAY_ID]
    refresh_token = entry.data[CONF_REFRESH_TOKEN]
    client_id = entry.data.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    token_mgr = TokenManager(client_id, refresh_token)
    client = PointtClient(gateway_id, token_mgr)

    coordinator = MX400Coordinator(hass, client, poll_interval, entry, token_mgr)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
