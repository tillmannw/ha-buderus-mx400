# Buderus MX400 for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for **Buderus MX400 (K40)** heating gateways. Communicates with the Bosch PoinTT cloud API to expose your heating system's sensors and controls as native Home Assistant entities.

## Features

- **Automatic entity discovery** — all available sensors and controls are created dynamically based on your system's capabilities
- **Sensors** — outdoor temperature, supply/return temperatures, system pressure, burner modulation, heat demand, burner starts, working time, compressor status, per-circuit room temperatures and setpoints, DHW temperatures, and more
- **Number controls** — writable temperature setpoints (manual, eco, comfort, DHW high/low) with min/max/step constraints from the API
- **Select controls** — operation modes (auto/manual/off), away mode, and any writable string resource with allowed values
- **Built-in OAuth login** — the setup flow opens the Bosch SingleKey ID login page directly, no manual token handling required
- **Automatic token rotation** — refresh tokens are persisted and rotated transparently on each use

## Supported Hardware

| Gateway | Internal Name | Support |
|---------|--------------|---------|
| Buderus MX400 | K40 | Full |
| Bosch MX400 | K40 | Full (same hardware) |

The MX400 connects to boilers and heat pumps via the EMS 2.0 bus. Any heating circuits, DHW circuits, and solar circuits detected by the gateway will be exposed automatically.

## Requirements

- A Buderus/Bosch MX400 (K40) gateway connected to the internet
- A Bosch SingleKey ID account (the same account used in the MyBuderus / Bosch Home Comfort app)
- Home Assistant 2024.1 or later
- HACS installed (for easy installation)

## Installation

### Via HACS (recommended)

1. Open **HACS** in Home Assistant
2. Click the three-dot menu (top right) and select **Custom repositories**
3. Add this repository URL and select category **Integration**
4. Click **Add**
5. Search for **Buderus MX400** in HACS and click **Install**
6. Restart Home Assistant

### Manual installation

1. Copy the `custom_components/buderus_mx400` directory into your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Setup

After installation and restart:

1. Go to **Settings > Devices & Services**
2. Click **+ Add Integration**
3. Search for **Buderus MX400**
4. Enter your **Gateway ID** (see [Finding your Gateway ID](#finding-your-gateway-id) below)
5. A new browser tab opens with a **"Log in with Bosch"** button
6. Click the button — a popup opens with the Bosch SingleKey ID login page
7. Log in with your Bosch account credentials
8. After login, capture the redirect URL (see [Capturing the redirect URL](#capturing-the-redirect-url) below)
9. Paste the URL into the form and click **Submit**
10. The integration exchanges the code for tokens and begins polling your heating system

### Finding your Gateway ID

The gateway ID is printed on the QR code sticker on your MX400 device. Scan the QR code — it decodes to a string like (most camera apps support the decoding of QR codes):

```
V:1;L:123456789;P:aAbB-c1dE-fGhI-JkLm;MAC:00-1a-2b-3d-4f-5g;N:MX400;
```

| Field | Meaning |
|-------|---------|
| `L` | **Gateway ID** (use this) |
| `P` | Gateway password (not needed for cloud access) |
| `MAC` | MAC address |
| `N` | Device name |

### Capturing the redirect URL

After logging in, the Bosch server tries to redirect your browser to `com.buderus.tt.dashtt://app/login?code=...` — this is a mobile app URL scheme that your desktop browser cannot open. You need to capture this URL manually:

1. **Before logging in**, open the browser Developer Tools in the login popup (press **F12**)
2. Go to the **Network** tab
3. Log in with your email and password
4. In the Network tab, look for a request to `callback?client_id=...` that shows a **302** status
5. Click on that request
6. In the **Response Headers**, find the `Location` header
7. Copy its value — it starts with `com.buderus.tt.dashtt://app/login?code=...`
8. Paste the full URL into the form on the integration setup page

## Entities

Entities are created dynamically based on what your heating system reports. The integration categorizes resources automatically:

| API Response Type | Writable | HA Entity | Example |
|-------------------|----------|-----------|---------|
| `floatValue` | No | Sensor | Outdoor temperature, system pressure |
| `floatValue` | Yes | Number | Room setpoint, DHW temperature |
| `integerValue` | Yes | Number | Boost duration |
| `stringValue` | No | Sensor | CH status, firmware version |
| `stringValue` + `allowedValues` | Yes | Select | Operation mode, away mode |

### Common entities

| Entity | Type | Description |
|--------|------|-------------|
| Outdoor Temperature | Sensor | Outside air temperature |
| Supply Temperature | Sensor | Boiler supply water temperature |
| Return Temperature | Sensor | Boiler return water temperature |
| System Pressure | Sensor | Heating system pressure (bar) |
| Burner Modulation | Sensor | Current burner modulation (%) |
| Heat Demand | Sensor | Current heat demand (%) |
| Burner Starts | Sensor | Total burner start count |
| Total Working Time | Sensor | Total boiler operating hours |
| HC1 Room Temperature | Sensor | Heating circuit 1 room temperature |
| HC1 Room Setpoint | Sensor | Heating circuit 1 current setpoint |
| HC1 Operation Mode | Select | auto / manual / off |
| HC1 Manual Room Setpoint | Number | Writable manual setpoint |
| HC1 Eco Temperature | Number | Eco mode temperature |
| HC1 Comfort Temperature | Number | Comfort mode temperature |
| DHW1 Temperature | Sensor | Hot water actual temperature |
| DHW1 Operation Mode | Select | auto / manual / off |
| DHW1 High Temperature | Number | DHW target temperature |
| Away Mode | Select | Enable/disable away mode |

The actual entities depend on your system — heat pump systems will show compressor status, defrost state, etc. Hybrid systems show additional heat source information.

## Configuration options

| Option | Default | Description |
|--------|---------|-------------|
| Gateway ID | *(required)* | Serial number from the MX400 device sticker |
| Poll interval | 60 | How often to query the Bosch cloud (seconds, 10–3600) |
| Client ID | `762162C0-...` | OAuth client ID (default works for Buderus; change only if needed) |

## Architecture

```
Home Assistant
  └── Buderus MX400 Integration
        ├── OAuth2 Token Manager (SingleKey ID)
        ├── PoinTT Cloud API Client
        │     ├── Bulk read (POST /bulk)
        │     └── Individual write (PUT /gateways/{id}/resource{path})
        ├── DataUpdateCoordinator (polls on interval)
        └── Dynamic entity creation
              ├── Sensors (read-only values)
              ├── Numbers (writable numeric values)
              └── Selects (writable string values with options)
```

The integration communicates exclusively via the Bosch PoinTT cloud API. The MX400 gateway does not expose a usable local REST API on the LAN — it connects to the Bosch cloud via an XMPP-based tunnel, and the cloud API proxies requests to the gateway.

## Troubleshooting

### Sensors show as "unavailable"

Check **Settings > System > Logs** and filter for `buderus_mx400`. Common causes:

- **Token refresh failed (400)** — the refresh token was invalidated. Remove the integration and add it again with a fresh login.
- **Connection timeout** — the Bosch cloud or your gateway may be temporarily unreachable. The integration will retry on the next poll cycle.

### Enable debug logging

Add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.buderus_mx400: debug
```

Restart HA to see detailed API request/response logging.

### "Cannot connect" during setup

- Verify the gateway ID is correct (from the QR code `L:` field)
- Ensure the gateway is online in the MyBuderus app
- The OAuth code may have expired — try the login flow again

## License

This project is not affiliated with Buderus, Bosch, or Bosch Thermotechnology. All product names and trademarks are the property of their respective owners.

This project has been vibe coded by Tillmann Werner. Pull requests welcome.
