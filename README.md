<p align="center">
  <img src="images/upzdownz-logo-white-text.png" width="35%">
</p>
<h2 align="center">Home Assistant Integration</h2>
<p align="center">
  Visualize your Home Assistant data in a clean, flexible and powerful dashboard. A HACS-compatible custom component that automatically collects "selected" data from Home Assistant and pushes it to your [UpzDownz Metric Dashboard](https://upzdownz.com). Configure everything through the Home Assistant UI — no YAML required.
</p>



---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
  - [Method A — HACS](#method-a--hacs-recommended)
  - [Method B — Manual](#method-b--manual)
- [Configuration](#configuration)
- [Data Source Types](#data-source-types)
  - [Sensors](#sensors)
  - [Battery Alerts](#battery-alerts)
  - [Unavailable Entities](#unavailable-entities)
  - [Calendar Events](#calendar-events)
  - [Weather](#weather)
  - [Custom](#custom)
- [Managing Sources](#managing-sources)
- [Diagnostic Sensors](#diagnostic-sensors)
- [Sync Intervals](#sync-intervals)
- [Error Notifications](#error-notifications)
- [Troubleshooting](#troubleshooting)
- [Security & Performance](#security--performance)

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | 2023.9 or later |
| HACS | Required for Method A — optional for manual install |
| UpzDownz account | Active account at [upzdownz.com](https://upzdownz.com) |
| API key | Found in UpzDownz Dashboard → Settings → API |
| Network | Home Assistant must be able to reach the internet over HTTPS |

---

## Installation

### Method A — HACS (Recommended)

1. In the Home Assistant sidebar, open **HACS**.
2. Click the three-dot menu in the top-right corner and select **Custom repositories**.
3. Enter the following and click **Add**:
   - Repository: `https://github.com/maglerod/upzdownz-ha`
   - Category: `Integration`
4. Search for **UpzDownz** in the HACS integration list, click it, then click **Download**.
5. Restart Home Assistant: **Settings → System → Restart**.

### Method B — Manual

1. Download `upzdownz_custom_component.zip` from the [latest release](https://github.com/maglerod/upzdownz-ha/releases).
2. Extract the archive. It contains a single folder named `upzdownz`.
3. Copy the folder to your Home Assistant configuration directory:

```
<config>/custom_components/upzdownz/
```

The final structure should look like this:

```
custom_components/
└── upzdownz/
    ├── __init__.py
    ├── api.py
    ├── config_flow.py
    ├── const.py
    ├── coordinator.py
    ├── icon.png
    ├── icon.svg
    ├── images/
    │   ├── icon.svg
    │   └── logo.svg
    ├── manifest.json
    ├── options_flow.py
    ├── sensor.py
    └── strings.json
```

4. Restart Home Assistant: **Settings → System → Restart**.

---

## Configuration

After restarting, set up the integration through the Home Assistant UI — no YAML needed.

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **UpzDownz** and click it.
3. Enter your API key. The integration validates it immediately.
4. Choose a source type to add. You can add multiple sources — click **Done — save and finish** when ready.

The integration begins its first sync immediately. Open your UpzDownz dashboard to confirm data is arriving.

> **Note:** Your API key is stored in Home Assistant's config entry and is never written to logs or exposed in the UI after initial entry.

---

## Data Source Types

Each source has an **UpzDownz Datasource name**, a **Sync interval**, and type-specific fields. The datasource name is what you connect your widgets to in the UpzDownz dashboard.

---

### Sensors

Sends a single snapshot row per sync cycle containing the current state of selected entities.

Adding a Sensor source is a two-step process:

**Step 1 — Select entities:** Search and pick entities from a dropdown. You can select as many as you need.

**Step 2 — Confirm field names:** Each selected entity gets a suggested field name (for example `sensor.living_room_temp` becomes `living_room_temp`). Edit these if needed — they become the column names in UpzDownz that you use when building widgets.

| Field | Example | Notes |
|---|---|---|
| UpzDownz Datasource name | `Living Room Climate` | The name you connect your widgets to |
| Sync interval | `5 minutes` | See [Sync Intervals](#sync-intervals) |
| Entities to include | *(searchable dropdown)* | Select one or more entities |

**Example payload:**

```json
{
  "temperature": 21.5,
  "humidity": 48.0,
  "recorded_at": "2024-01-15T10:00:00Z"
}
```

---

### Battery Alerts

Automatically scans all entities with `device_class: battery` and reports any device below the configured threshold. No manual entity selection required.

| Field | Example | Notes |
|---|---|---|
| UpzDownz Datasource name | `Battery Alerts` | The name you connect your widgets to |
| Sync interval | `30 minutes` | Battery levels change slowly |
| Battery threshold (%) | `20` | Slider from 5–50%. Devices **below** this value are reported. Setting it to 20 means any device below 20% appears in your dashboard. |

**Example payload** (one row per affected device):

```json
{
  "entity_id": "sensor.motion_battery",
  "friendly_name": "Motion Sensor",
  "battery_level": 8,
  "recorded_at": "2024-01-15T10:00:00Z"
}
```

---

### Unavailable Entities

Reports all entities currently in `unavailable` or `unknown` state. Useful for detecting disconnected devices or broken integrations.

| Field | Example | Notes |
|---|---|---|
| UpzDownz Datasource name | `Unavailable Devices` | The name you connect your widgets to |
| Sync interval | `15 minutes` | Shorter intervals give faster alerts |
| Excluded domains | `group, scene, automation` | Comma-separated. These domains are skipped entirely. |

**Default excluded domains** (pre-filled):

```
group, scene, automation, script, zone, input_boolean, input_number, input_select, input_text
```

**Example payload** (one row per unavailable entity):

```json
{
  "entity_id": "sensor.door_contact",
  "domain": "binary_sensor",
  "friendly_name": "Front Door",
  "last_changed": "2024-01-15T08:00:00Z",
  "recorded_at": "2024-01-15T10:00:00Z"
}
```

---

### Calendar Events

Fetches upcoming events for the next 7 days from one or more `calendar.*` entities. Sends one row per event. Requires Home Assistant 2023.9 or later.

| Field | Example | Notes |
|---|---|---|
| UpzDownz Datasource name | `Calendar Events` | The name you connect your widgets to |
| Sync interval | `1 hour` | Calendar events change infrequently |
| Calendar entities | *(searchable dropdown, filtered to `calendar.*`)* | Select one or more calendar entities |

**Example payload** (one row per event):

```json
{
  "calendar": "calendar.home",
  "summary": "Bin collection",
  "start": "2024-01-20T08:00:00",
  "end": "2024-01-20T09:00:00",
  "all_day": true,
  "recorded_at": "2024-01-15T10:00:00Z"
}
```

---

### Weather

Fetches current conditions plus a daily forecast from a `weather.*` entity. Sends one row for current conditions and one row per forecast day. Requires Home Assistant 2023.9 or later.

| Field | Example | Notes |
|---|---|---|
| UpzDownz Datasource name | `Home Weather` | The name you connect your widgets to |
| Sync interval | `1 hour` | Hourly is sufficient for weather data |
| Weather entity | *(searchable dropdown, filtered to `weather.*`)* | Select a single weather entity |

**Example payload** (current conditions row):

```json
{
  "type": "current",
  "condition": "cloudy",
  "temperature": 5.2,
  "humidity": 78,
  "wind_speed": 12.5,
  "pressure": 1013.0,
  "recorded_at": "2024-01-15T10:00:00Z"
}
```

---

### Custom

Full control over which entities are included and what their field names are. Identical flow to Sensors — two-step entity picker followed by field name confirmation.

| Field | Example | Notes |
|---|---|---|
| UpzDownz Datasource name | `Energy Monitor` | The name you connect your widgets to |
| Sync interval | `5 minutes` | Choose based on how fast your data changes |
| Entities to include | *(searchable dropdown)* | Select one or more entities |

---

## Managing Sources

You can add or remove data sources at any time without reinstalling or restarting:

1. Go to **Settings → Devices & Services**.
2. Find the **UpzDownz** card and click **Configure**.
3. Use the menu to add a new source or remove an existing one.
4. Click **Save** — the integration reloads automatically.

> **Note:** Removing a source in Home Assistant does not delete the source or its historical data in UpzDownz. Manage that from the UpzDownz dashboard.

---

## Diagnostic Sensors

The integration creates one sensor entity per data source. These appear in Home Assistant and reflect the live sync status.

| Attribute | Example | Description |
|---|---|---|
| State | `ok` | `ok` / `error` / `no_data` — result of the last sync cycle |
| `last_sync` | `2024-01-15T10:05:00Z` | Timestamp of the last successful data push |
| `rows_sent` | `1247` | Cumulative rows pushed since Home Assistant started |
| `source_id` | `uuid-...` | The UpzDownz source ID — useful for debugging |
| `source_type` | `battery` | The type of this data source |

Sensor names follow the pattern `sensor.upzdownz_<source_name>`. For example, a source named `Battery Alerts` creates `sensor.upzdownz_battery_alerts`.

**Example automation — alert when a source enters error state:**

```yaml
trigger:
  - platform: state
    entity_id: sensor.upzdownz_battery_alerts
    to: "error"
action:
  - service: notify.mobile_app
    data:
      message: "UpzDownz sync failed for Battery Alerts"
```

---

## Sync Intervals

| Interval | Rows/day (per source) | Recommended for |
|---|---|---|
| 1 minute | 1 440 | High-frequency energy or environmental sensors |
| 5 minutes | 288 | Temperature, humidity, motion — default |
| 15 minutes | 96 | Slow-changing sensors, unavailable entity checks |
| 30 minutes | 48 | Battery levels, presence |
| 1 hour | 24 | Weather, calendar events |

> Your UpzDownz plan determines your row retention period (typically 7–90 days). If you reach your plan limit, the integration skips that cycle and retries automatically on the next run — and you will receive a persistent notification in Home Assistant.

---

## Error Notifications

The integration surfaces errors directly in the Home Assistant UI as **persistent notifications** (the bell icon in the sidebar) — you do not need to read system logs to know something went wrong.

| Situation | What you see in HA |
|---|---|
| Invalid or expired API key | Notification with instructions for where to re-enter the key |
| Plan row limit reached | Notification explaining the limit and how to resolve it |
| Connection error on first sync | Notification that the integration will keep retrying automatically |

---

## Troubleshooting

### No data appearing in UpzDownz

- Check the diagnostic sensor state — it should read `ok` after the first sync cycle.
- Check for persistent notifications in Home Assistant (bell icon in the sidebar).
- Verify the API key in **Settings → Devices & Services → UpzDownz → Configure**.
- Check Home Assistant logs: **Settings → System → Logs**, filter for `upzdownz`.
- Confirm that your Home Assistant instance can reach the internet over HTTPS.

### Diagnostic sensor shows `error`

| Situation | Solution |
|---|---|
| Invalid or expired API key | Re-enter the key via **Configure** in the integration |
| Plan row limit reached | Upgrade your UpzDownz plan or reduce sync frequency |
| Network / connection error | Check connectivity — the integration retries automatically |
| Calendar or weather service fails | Verify the entity ID and confirm HA is 2023.9 or later |

### Integration does not appear after installation

- Confirm the folder is named exactly `upzdownz` (all lowercase).
- Confirm the path is `custom_components/upzdownz/`, not `custom_components/upzdownz/upzdownz/`.
- Perform a full restart of Home Assistant.
- Check the HA startup log for any Python errors mentioning `upzdownz`.

---

## Security & Performance

**Performance:** The integration has no measurable impact on Home Assistant. All data collection is asynchronous, runs on a configurable schedule, and uses Home Assistant's shared HTTP session and coordinator pattern — the same approach used by all official integrations.

**Security:**

- The integration only **reads** from Home Assistant — it never writes entity states, triggers automations, or modifies configuration.
- All communication is **outbound HTTPS only** — no incoming connections, no open ports, no webhooks.
- The API key is stored in the same way as all other HA integrations (Spotify, Philips Hue, Google, etc.).
- No external Python packages are required — only `aiohttp`, which is already part of Home Assistant.

---

## API Endpoint

```
https://ujpgoljgvddzlwqepcou.supabase.co/functions/v1/metric-ingest
```

Authentication uses the HTTP header `x-api-key: <your_api_key>` on every request. All timestamps are sent in ISO 8601 format (`2024-01-15T10:00:00Z`).

**Supported schema field types:**

| Type | Used for |
|---|---|
| `string` | Text values, entity IDs, condition strings |
| `decimal` | Float numbers — temperature, battery percentage, wind speed |
| `integer` | Whole numbers — counts |
| `boolean` | True/false values — on/off states, all-day flags |

---

## Links

- [UpzDownz Dashboard](https://upzdownz.com)
- [Issue Tracker](https://github.com/maglerod/upzdownz-ha/issues)
- [HACS](https://hacs.xyz)
