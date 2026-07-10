# GeoShake — Home Assistant Integration

Earthquake early-warning for Home Assistant. Connects directly to the GeoShake
network over secure MQTT (TLS) — **no YAML, no local broker, and it does not use
Home Assistant's MQTT integration slot**.

## Entities

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.geoshake_network_earthquake` | safety | ON when the GeoShake network confirms an earthquake (3+ stations); auto-clears 120 s after the last event |
| `sensor.geoshake_network_last_event` | timestamp | Origin time of the last confirmed event; attributes: intensity class, stations, max PGA, coordinates |
| `binary_sensor.geoshake_network_connection` | connectivity (diagnostic) | Live MQTT connection status |

## Install (HACS)

1. HACS → **⋮ → Custom repositories** → add this repository URL, category **Integration**.
2. Search **GeoShake** in HACS → **Download** → restart Home Assistant.
3. **Settings → Devices & Services → + Add Integration → GeoShake.**
4. Enter the **GeoShake MQTT credentials** that came with your device. Done — the
   earthquake sensor appears automatically.

Then create an automation: trigger on `Earthquake` turning **On** (see the
[GeoShake guide](https://geoshake.org) for examples — sirens, lights, TTS announcements).

### Migrating from the manual MQTT setup

If you followed the old guide (manual MQTT integration + `configuration.yaml` block):

1. Remove the `mqtt: binary_sensor:` GeoShake block from `configuration.yaml`.
2. If the GeoShake broker occupied your MQTT integration, you can now delete that MQTT
   config (or repoint it to your own local broker) — this integration connects on its own.
3. Update your automations to the new entity (`binary_sensor.geoshake_network_earthquake`).

## Publishing (maintainers)

HACS requires a dedicated public GitHub repo with this layout at the **repo root**:

```
hacs.json
README.md
custom_components/geoshake/...
```

Steps: create public repo `geoshake-homeassistant` → copy this folder's contents
(without `.venv`, `tests` optional but recommended) → tag a release (`v0.1.0`).
Users add the repo URL as a HACS custom repository. Later: submit to HACS default
store (requirements: repo topics, brands PR) and eventually Home Assistant Core.

## Development

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python pytest homeassistant aiomqtt
.venv/bin/python -m pytest tests/        # pure-core tests (no HA needed to run)
```

Architecture: pure core (`const.py` — payload parsing, dedup, backoff; fully unit-tested)
+ thin HA shell (`mqtt_client.py`, entities). Alarm semantics mirror the GeoShake cloud
worker: new event → ON, 120 s auto-clear with reset, `event_id` dedup (QoS 1 redelivery).

Brand images live in `custom_components/geoshake/brand/` (HA 2026.3+ Brands Proxy API —
local images take priority over the brands CDN; no `home-assistant/brands` PR needed).
On older HA versions a generic placeholder is shown instead.
