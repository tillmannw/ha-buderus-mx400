"""Constants for Buderus MX400 integration."""

DOMAIN = "buderus_mx400"

CONF_GATEWAY_ID = "gateway_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_CLIENT_ID = "client_id"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_CLIENT_ID = "762162C0-FA2D-4540-AE66-6489F189FADC"
DEFAULT_POLL_INTERVAL = 60

SKID_DISCOVERY_URL = "https://singlekey-id.com/auth/.well-known/openid-configuration"
POINTT_BASE_URL = "https://pointt-api.bosch-thermotechnology.com/pointt-api/api/v1/"

SENSOR_FAULT_VALUE = -3276.8

MANUFACTURER = "Buderus"
MODEL = "MX400 (K40)"
