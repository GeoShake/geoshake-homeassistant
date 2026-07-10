"""GeoShake entegrasyonu — kurulum/sökme yaşam döngüsü.

MQTT istemcisi entry başına BİR kez kurulur; entity platformları (binary_sensor,
sensor) callback'lere abone olur. Unload'da istemci temiz kapatılır (reload güvenli).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_BROKER, DOMAIN, GeoShakeEvent
from .mqtt_client import EventCallback, GeoShakeMqttClient, StatusCallback

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


@dataclass
class GeoShakeData:
    """Entry runtime verisi: istemci + entity aboneleri + son durum."""

    # Kuruluş sırası gereği None başlar (callback'ler data'ya bağlanır, client sonra).
    client: GeoShakeMqttClient | None = None
    connected: bool = False
    last_event: GeoShakeEvent | None = None
    # Entity'ler kendilerini buraya yazar (add) / unload'da temizlenir.
    event_listeners: list[EventCallback] = field(default_factory=list)
    status_listeners: list[StatusCallback] = field(default_factory=list)

    def dispatch_event(self, event: GeoShakeEvent) -> None:
        self.last_event = event
        for listener in list(self.event_listeners):
            listener(event)

    def dispatch_status(self, connected: bool) -> None:
        self.connected = connected
        for listener in list(self.status_listeners):
            listener(connected)


# `type` alias DEĞİL (3.12+ sözdizimi) — düz alias: 3.11'de de derlenir.
GeoShakeConfigEntry = ConfigEntry[GeoShakeData]


async def async_setup_entry(hass: HomeAssistant, entry: GeoShakeConfigEntry) -> bool:
    data = GeoShakeData()

    client = GeoShakeMqttClient(
        broker=entry.data[CONF_BROKER],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        # Callback'ler MQTT task'ından gelir (aynı event loop) — thread-safe kaygısı yok.
        on_event=data.dispatch_event,
        on_status=data.dispatch_status,
    )
    data.client = client
    entry.runtime_data = data

    # Entity'ler listener'lara abone OLDUKTAN sonra dinlemeye başla — ilk olayın
    # EarthquakeAlarm tarafından kaçırılabileceği mikro-pencereyi kapatır.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    client.start()
    # Options (off_delay) değişince entry'yi yeniden yükle — entity'ler yeni değeri alsın.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: GeoShakeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GeoShakeConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data.client is not None:
        await entry.runtime_data.client.stop()
    return unload_ok
