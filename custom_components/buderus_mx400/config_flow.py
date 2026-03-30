"""Config flow for Buderus MX400 integration."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import urllib.parse
from typing import Any

import requests
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api import PointtClient, TokenManager
from .const import (
    CONF_CLIENT_ID,
    CONF_GATEWAY_ID,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    DEFAULT_CLIENT_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    SKID_DISCOVERY_URL,
)

_LOGGER = logging.getLogger(__name__)

REDIRECT_URI = "com.buderus.tt.dashtt://app/login"
AUTH_CALLBACK_PATH = "/api/buderus_mx400/callback"
SCOPES = (
    "openid email profile offline_access "
    "pointt.gateway.claiming pointt.gateway.removal pointt.gateway.list "
    "pointt.gateway.users pointt.gateway.resource.dashapp "
    "pointt.castt.flow.token-exchange bacon hcc.tariff.read"
)


def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# Store flow state globally so the callback view can find it
_pending_flows: dict[str, dict[str, Any]] = {}


class OAuth2CallbackView(HomeAssistantView):
    """Handle the OAuth callback by showing a page where the user pastes the redirect URL."""

    url = AUTH_CALLBACK_PATH
    name = "api:buderus_mx400:callback"
    requires_auth = False

    async def get(self, request):
        """Serve a page that captures the redirect URL."""
        from aiohttp import web

        flow_id = request.query.get("flow_id", "")

        html = f"""<!DOCTYPE html>
<html>
<head><title>Buderus MX400 Login</title></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px;">
<h2>Buderus MX400 — Bosch Login</h2>
<div id="step1">
  <p>Click the button below to log in with your Bosch SingleKey ID account.</p>
  <p><button id="login-btn" onclick="openLogin()"
     style="padding:12px 24px; background:#03a9f4; color:white; border:none; border-radius:4px; font-size:16px; cursor:pointer;">
     Log in with Bosch
  </button></p>
</div>
<div id="step2" style="display:none;">
  <p style="color:#ff9800; font-size:18px;"><b>Waiting for login...</b></p>
  <p>Complete the login in the popup window. If a dialog asks to open <code>xdg-open</code>,
  click <b>Cancel</b> and copy the URL from the popup's address bar instead.</p>
  <hr style="margin: 20px 0;">
  <p>Paste the redirect URL here (starts with <code>com.buderus.tt.dashtt://</code>):</p>
  <form method="POST" action="{AUTH_CALLBACK_PATH}">
    <input type="hidden" name="flow_id" value="{flow_id}">
    <input type="text" id="redirect_url" name="redirect_url"
           placeholder="com.buderus.tt.dashtt://app/login?code=..."
           style="width:100%; padding:10px; font-size:14px; margin-bottom:10px;">
    <button type="submit" id="submit-btn"
            style="padding:10px 24px; background:#4caf50; color:white; border:none; border-radius:4px; font-size:16px; cursor:pointer;">
      Submit
    </button>
  </form>
</div>
<div id="step-auto" style="display:none;">
  <p style="color:#4caf50; font-size:18px;"><b>Login captured! Submitting...</b></p>
</div>
<script>
  var authUrl = '';
  var loginWindow = null;

  fetch('{AUTH_CALLBACK_PATH}/auth_url?flow_id={flow_id}')
    .then(r => r.json())
    .then(d => {{ authUrl = d.auth_url; }});

  function openLogin() {{
    document.getElementById('step1').style.display = 'none';
    document.getElementById('step2').style.display = 'block';
    loginWindow = window.open(authUrl, 'bosch_login', 'width=500,height=700');
    pollPopup();
  }}

  function pollPopup() {{
    if (!loginWindow) return;
    try {{
      var url = loginWindow.location.href;
      if (url && url.startsWith('com.buderus.tt.dashtt://')) {{
        loginWindow.close();
        document.getElementById('redirect_url').value = url;
        document.getElementById('step2').style.display = 'none';
        document.getElementById('step-auto').style.display = 'block';
        document.querySelector('form').submit();
        return;
      }}
    }} catch(e) {{
      // cross-origin — login still in progress, this is expected
    }}
    if (loginWindow.closed) {{
      // Popup was closed without capturing — user needs to paste manually
      document.getElementById('redirect_url').focus();
      return;
    }}
    setTimeout(pollPopup, 500);
  }}
</script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def post(self, request):
        """Handle the pasted redirect URL and advance the config flow."""
        from aiohttp import web

        data = await request.post()
        flow_id = data.get("flow_id", "")
        redirect_url = data.get("redirect_url", "").strip()

        if flow_id in _pending_flows:
            _pending_flows[flow_id]["redirect_url"] = redirect_url
            _pending_flows[flow_id]["done"] = True

        # Advance the config flow — this tells HA the external step is complete
        hass = request.app["hass"]
        try:
            await hass.config_entries.flow.async_configure(flow_id=flow_id)
        except Exception:
            _LOGGER.debug("Flow advance failed (may already be done)", exc_info=True)

        html = """<!DOCTYPE html>
<html><body style="font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px;">
<h2>Done!</h2>
<p>You can close this tab and return to Home Assistant.</p>
</body></html>"""
        return web.Response(text=html, content_type="text/html")


class OAuth2AuthURLView(HomeAssistantView):
    """Return the auth URL for a pending flow."""

    url = AUTH_CALLBACK_PATH + "/auth_url"
    name = "api:buderus_mx400:auth_url"
    requires_auth = False

    async def get(self, request):
        from aiohttp import web

        flow_id = request.query.get("flow_id", "")
        flow = _pending_flows.get(flow_id, {})
        return web.json_response({"auth_url": flow.get("auth_url", "")})


class BuderusMX400ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Buderus MX400."""

    VERSION = 1

    def __init__(self) -> None:
        self._gateway_id: str = ""
        self._poll_interval: int = DEFAULT_POLL_INTERVAL
        self._client_id: str = DEFAULT_CLIENT_ID
        self._code_verifier: str = ""
        self._oauth_state: str = ""
        self._auth_url: str = ""
        self._token_endpoint: str = ""
        self._views_registered = False

    def _register_views(self) -> None:
        if self._views_registered:
            return
        try:
            self.hass.http.register_view(OAuth2CallbackView)
            self.hass.http.register_view(OAuth2AuthURLView)
        except Exception:
            pass  # Already registered
        self._views_registered = True

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._gateway_id = user_input[CONF_GATEWAY_ID]
            self._poll_interval = user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            self._client_id = user_input.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID)

            await self.async_set_unique_id(self._gateway_id)
            self._abort_if_unique_id_configured()

            try:
                discovery = await self.hass.async_add_executor_job(self._fetch_discovery)
                authorization_endpoint = discovery["authorization_endpoint"]
                self._token_endpoint = discovery["token_endpoint"]
            except Exception:
                _LOGGER.exception("Failed to discover OIDC endpoints")
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="user", data_schema=self._user_schema(), errors=errors
                )

            self._code_verifier = _generate_code_verifier()
            code_challenge = _generate_code_challenge(self._code_verifier)
            self._oauth_state = secrets.token_urlsafe(32)

            params = {
                "client_id": self._client_id,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "state": self._oauth_state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "login",
            }
            self._auth_url = authorization_endpoint + "?" + urllib.parse.urlencode(params)

            # Register HTTP views and store flow state
            self._register_views()
            _pending_flows[self.flow_id] = {
                "auth_url": self._auth_url,
                "redirect_url": None,
                "done": False,
            }

            return self.async_external_step(
                step_id="auth",
                url=f"{AUTH_CALLBACK_PATH}?flow_id={self.flow_id}",
            )

        return self.async_show_form(
            step_id="user", data_schema=self._user_schema(), errors=errors
        )

    @staticmethod
    def _user_schema() -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_GATEWAY_ID): str,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
                    int, vol.Range(min=10, max=3600)
                ),
                vol.Optional(CONF_CLIENT_ID, default=DEFAULT_CLIENT_ID): str,
            }
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait for the user to complete OAuth and paste the redirect URL."""
        flow = _pending_flows.get(self.flow_id, {})

        if not flow.get("done"):
            # Not done yet — HA will poll this step
            return self.async_external_step_done(next_step_id="finish")

        return self.async_external_step_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Exchange the authorization code for tokens."""
        flow = _pending_flows.pop(self.flow_id, {})
        redirect_url = flow.get("redirect_url", "")

        if not redirect_url:
            return self.async_abort(reason="no_url")

        parsed = urllib.parse.urlparse(redirect_url)
        qs = urllib.parse.parse_qs(parsed.query)

        if "error" in qs:
            _LOGGER.error("OAuth error: %s", qs["error"][0])
            return self.async_abort(reason="invalid_auth")

        if "code" not in qs:
            return self.async_abort(reason="no_code")

        code = qs["code"][0]

        try:
            token_data = await self.hass.async_add_executor_job(
                self._exchange_code, code
            )
        except Exception:
            _LOGGER.exception("Token exchange failed")
            return self.async_abort(reason="invalid_auth")

        refresh_token = token_data["refresh_token"]

        # Verify gateway is reachable
        token_mgr = TokenManager(self._client_id, refresh_token)
        token_mgr._access_token = token_data["access_token"]
        token_mgr._expires_at = time.time() + token_data.get("expires_in", 3600) - 60

        client = PointtClient(self._gateway_id, token_mgr)
        online = await self.hass.async_add_executor_job(client.is_online)

        if not online:
            return self.async_abort(reason="cannot_connect")

        return self.async_create_entry(
            title=f"MX400 ({self._gateway_id})",
            data={
                CONF_GATEWAY_ID: self._gateway_id,
                CONF_REFRESH_TOKEN: token_mgr.refresh_token,
                CONF_CLIENT_ID: self._client_id,
                CONF_POLL_INTERVAL: self._poll_interval,
            },
        )

    @staticmethod
    def _fetch_discovery() -> dict:
        resp = requests.get(SKID_DISCOVERY_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _exchange_code(self, code: str) -> dict:
        resp = requests.post(
            self._token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": self._client_id,
                "code_verifier": self._code_verifier,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            _LOGGER.error("Token exchange: %s %s", resp.status_code, resp.text[:500])
            raise RuntimeError(f"Token exchange failed: {resp.status_code}")
        return resp.json()
