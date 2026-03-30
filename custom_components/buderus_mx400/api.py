"""Bosch PoinTT cloud API client for MX400 gateways."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .const import POINTT_BASE_URL, SKID_DISCOVERY_URL

_LOGGER = logging.getLogger(__name__)

HTTP_TIMEOUT = (10, 30)


class TokenManager:
    """Manages OAuth tokens for Bosch SingleKey ID."""

    def __init__(self, client_id: str, refresh_token: str) -> None:
        self.client_id = client_id
        self._access_token: str | None = None
        self._refresh_token = refresh_token
        self._expires_at: float = 0
        self._token_endpoint: str | None = None

    def _discover(self) -> None:
        if self._token_endpoint:
            return
        resp = requests.get(SKID_DISCOVERY_URL, timeout=10)
        resp.raise_for_status()
        self._token_endpoint = resp.json()["token_endpoint"]

    def _refresh(self) -> None:
        self._discover()
        _LOGGER.debug("Refreshing OAuth token")
        resp = requests.post(
            self._token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            _LOGGER.error(
                "Token refresh failed: HTTP %s, body: %s",
                resp.status_code,
                resp.text[:500],
            )
            raise RuntimeError(f"Token refresh failed: {resp.status_code}")
        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._expires_at = time.time() + data.get("expires_in", 3600) - 60

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    def get_access_token(self) -> str:
        if not self._access_token or time.time() >= self._expires_at:
            self._refresh()
        return self._access_token


class PointtClient:
    """Client for the Bosch PoinTT cloud API."""

    def __init__(self, gateway_id: str, token_manager: TokenManager) -> None:
        self.gateway_id = gateway_id
        self.token_manager = token_manager
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    def read(self, path: str) -> dict | None:
        url = f"{POINTT_BASE_URL}gateways/{self.gateway_id}/resource{path}"
        try:
            resp = self.session.get(url, headers=self._auth(), timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            _LOGGER.warning("Failed to read %s", path, exc_info=True)
        return None

    def read_many(self, paths: list[str]) -> dict[str, dict | None]:
        url = f"{POINTT_BASE_URL}bulk"
        body = [{"gatewayId": self.gateway_id, "resourcePaths": paths}]
        results: dict[str, dict | None] = {}
        try:
            resp = self.session.post(
                url, json=body, headers=self._auth(), timeout=HTTP_TIMEOUT
            )
            if resp.status_code != 200:
                return {p: self.read(p) for p in paths}
            data = resp.json()
            for entry in data:
                for rp in entry.get("resourcePaths", []):
                    path = rp.get("resourcePath", "")
                    gw = rp.get("gatewayResponse")
                    if gw and gw.get("status") == 200:
                        results[path] = gw.get("payload")
                    else:
                        results[path] = None
        except Exception:
            _LOGGER.warning("Bulk read failed", exc_info=True)
            return {p: self.read(p) for p in paths}
        return results

    def write(self, path: str, value: Any) -> bool:
        url = f"{POINTT_BASE_URL}gateways/{self.gateway_id}/resource{path}"
        try:
            resp = self.session.put(
                url, json={"value": value}, headers=self._auth(), timeout=HTTP_TIMEOUT
            )
            return resp.status_code in (200, 204)
        except Exception:
            _LOGGER.error("Write failed for %s", path, exc_info=True)
            return False

    def is_online(self) -> bool:
        result = self.read("/gateway/uuid")
        return result is not None
