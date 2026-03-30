"""DataUpdateCoordinator for Buderus MX400."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PointtClient, TokenManager
from .const import CONF_REFRESH_TOKEN, DOMAIN, SENSOR_FAULT_VALUE

_LOGGER = logging.getLogger(__name__)

# Full resource catalog — every known path grouped by subsystem
STATIC_PATHS = [
    "/gateway/uuid",
    "/gateway/versionFirmware",
    "/gateway/dataProcessing/status",
    "/system/info",
    "/system/bus",
    "/system/brand",
    "/system/country",
    "/system/dateTime",
    "/system/awayMode/enabled",
    "/system/powerGuard/active",
    "/system/powerLimitation/active",
    "/system/iSRC/supportStatus",
    "/system/iSRC/installationStatus",
    "/system/energyTariff/electricity",
    "/system/energyTariff/gas",
    "/system/energyTariff/oil",
    "/system/energyTariff/pv",
    "/system/sensors/temperatures/outdoor_t1",
    "/system/appliance/model",
    "/system/appliance/versionFirmware",
    "/system/location/coordinates",
    "/system/lowNoise/mode",
    "/system/lowNoise/duration",
    "/system/globalSeasonOptimizer/currentMode",
    "/heatSources/info",
    "/heatSources/type",
    "/heatSources/actualSupplyTemperature",
    "/heatSources/actualHeatDemand",
    "/heatSources/actualModulation",
    "/heatSources/chStatus",
    "/heatSources/currentEmergencyMode",
    "/heatSources/emStatus",
    "/heatSources/standbyMode",
    "/heatSources/systemPressure",
    "/heatSources/systemPressureRange",
    "/heatSources/returnTemperature",
    "/heatSources/numberOfStarts",
    "/heatSources/workingTime/totalSystem",
    "/heatSources/compressor/status",
    "/heatSources/pvContactState",
    "/heatSources/Source/eHeater/status",
    "/heatSources/passiveCooling/inflowTemp",
    "/heatSources/hs1/type",
    "/heatSources/hs1/heatPumpType",
    "/heatSources/hs1/defrostActive",
    "/heatSources/hs1/numberOfStarts",
    "/heatSources/hs1/brineCircuit/collectorOutflowTemp",
    "/heatSources/hs1/brineCircuit/collectorInflowTemp",
    "/heatSources/hs2/type",
    "/heatSources/hs2/heatPumpType",
    "/heatSources/hs2/defrostActive",
    "/heatSources/hs2/numberOfStarts",
    "/heatSources/hybrid/activeHeatSource",
    "/heatSources/hybrid/controlStrategy",
    "/heatSources/hybrid/outdoorStatus",
    "/heatSources/hybrid/outdoorVariant",
    "/heatSources/hybrid/reminderDate",
    "/heatSources/hybrid/reminderEnable",
    "/heatSources/hybrid/reminderLapsed",
    "/ventilation/zone1/operationMode",
    "/ventilation/zone1/exhaustFanLevel",
    "/ventilation/zone1/ventilationLevels",
    "/ventilation/zone1/switchPrograms/cp",
    "/ventilation/zone1/sensors/supplyTemp",
    "/ventilation/zone1/maxRelativeHumidity",
    "/ventilation/zone1/maxIndoorAirQuality",
    "/ventilation/zone1/filter/remainingTime",
    "/holidayMode/activeModes",
    "/holidayMode/configuration",
    "/holidayMode/list",
    "/solarCircuits/sc1/collectorTemperature",
    "/solarCircuits/sc1/pumpModulation",
    "/solarCircuits/sc1/dhwTankBottomTemperature",
    "/solarCircuits/sc1/maxCylinderTemperature",
    "/solarCircuits/sc1/maxTemperatureReached",
    "/notifications",
]

HC_SUFFIXES = [
    "/heatingType",
    "/currentRoomSetpoint",
    "/roomTemperature",
    "/currentSuWiMode",
    "/heatCoolMode",
    "/operationMode",
    "/manualRoomSetpoint",
    "/activeSwitchProgram",
    "/switchProgramMode",
    "/temporaryRoomSetpoint",
    "/temperatureLevels/eco",
    "/temperatureLevels/comfort2",
    "/controlType",
    "/heatingCircuitType",
    "/boostMode",
    "/boostDuration",
    "/boostRemainingTime",
    "/boostTemperature",
    "/setpointOptimization",
]

DHW_SUFFIXES = [
    "/actualTemp",
    "/charge",
    "/chargeDuration",
    "/chargeRemainingTime",
    "/currentTemperatureLevel",
    "/name",
    "/operationMode",
    "/outTemp",
    "/singleChargeSetpoint",
    "/switchProgram/A",
    "/temperatureLevels/eco",
    "/temperatureLevels/high",
    "/temperatureLevels/low",
    "/temperatureLevels/off",
    "/dhwType",
]


class MX400Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the PoinTT API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PointtClient,
        poll_interval: int,
        entry: ConfigEntry,
        token_manager: TokenManager,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self.entry = entry
        self.token_manager = token_manager
        self.heating_circuits: list[str] = []
        self.dhw_circuits: list[str] = []
        self.firmware: str = "unknown"
        self.available_paths: set[str] = set()
        self._discovered = False

    async def _async_setup(self) -> None:
        if self._discovered:
            return
        data = await self.hass.async_add_executor_job(
            self.client.read_many,
            ["/heatingCircuits", "/dhwCircuits", "/gateway/versionFirmware"],
        )

        hc = data.get("/heatingCircuits")
        if hc and hc.get("type") == "refEnum":
            self.heating_circuits = [r["id"] for r in hc.get("references", [])]

        dhw = data.get("/dhwCircuits")
        if dhw and dhw.get("type") == "refEnum":
            self.dhw_circuits = [r["id"] for r in dhw.get("references", [])]

        fw = data.get("/gateway/versionFirmware")
        if fw:
            self.firmware = fw.get("value", "unknown")

        _LOGGER.info(
            "Discovered HC=%s DHW=%s FW=%s",
            self.heating_circuits,
            self.dhw_circuits,
            self.firmware,
        )
        self._discovered = True

    def _build_paths(self) -> list[str]:
        paths = list(STATIC_PATHS)
        for hc in self.heating_circuits:
            for suffix in HC_SUFFIXES:
                paths.append(f"{hc}{suffix}")
        for dhw in self.dhw_circuits:
            for suffix in DHW_SUFFIXES:
                paths.append(f"{dhw}{suffix}")
        return paths

    def _persist_token_if_rotated(self) -> None:
        current_rt = self.token_manager.refresh_token
        if current_rt != self.entry.data.get(CONF_REFRESH_TOKEN):
            _LOGGER.debug("Persisting rotated refresh token")
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_REFRESH_TOKEN: current_rt},
            )

    async def _async_update_data(self) -> dict[str, Any]:
        await self._async_setup()
        paths = self._build_paths()

        # Read in batches
        all_raw: dict[str, dict | None] = {}
        batch_size = 50
        try:
            for i in range(0, len(paths), batch_size):
                batch = paths[i : i + batch_size]
                all_raw.update(
                    await self.hass.async_add_executor_job(
                        self.client.read_many, batch
                    )
                )
        except Exception as err:
            raise UpdateFailed(f"Error polling PoinTT API: {err}") from err
        finally:
            self._persist_token_if_rotated()

        result: dict[str, Any] = {}
        for path, payload in all_raw.items():
            if payload is None:
                continue
            value = payload.get("value")
            if isinstance(value, (int, float)) and value == SENSOR_FAULT_VALUE:
                continue
            result[path] = payload

        self.available_paths = set(result.keys())
        return result
