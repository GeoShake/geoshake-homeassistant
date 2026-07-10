"""GeoShake binary sensörleri.

 · earthquake (safety): yeni olay → ON; off_delay (vars. 120sn) sonra otomatik OFF;
   yeni olay timer'ı RESET eder (GH worker semantiği). Öznitelikler: olay detayı.
 · connection (connectivity, diagnostic): MQTT bağlantı durumu — destek/teşhis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import GeoShakeConfigEntry
from .const import (
    CONF_OFF_DELAY,
    CONF_RADIUS_KM,
    DEFAULT_OFF_DELAY_S,
    DEFAULT_RADIUS_KM,
    GeoShakeEvent,
    event_within,
    haversine_km,
)
from .entity import GeoShakeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoShakeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EarthquakeAlarm(entry), ConnectionStatus(entry)])


def event_attributes(event: GeoShakeEvent, home: tuple[float, float] | None = None) -> dict[str, Any]:
    """Olay → entity öznitelikleri (earthquake + last_event aynı sözlüğü kullanır).

    GH3c: home (lat, lon) verilirse olayın eve uzaklığı da eklenir (distance_km).
    """
    attrs: dict[str, Any] = {
        "event_id": event.event_id,
        "origin": datetime.fromtimestamp(event.origin_ms / 1000, tz=timezone.utc).isoformat(),
        "latitude": event.lat,
        "longitude": event.lon,
        "stations": event.n_stations,
        "intensity_class": event.intensity_class,
        "max_pga": event.max_pga,
    }
    if home is not None:
        attrs["distance_km"] = round(haversine_km(event.lat, event.lon, home[0], home[1]), 1)
    return attrs


class EarthquakeAlarm(GeoShakeEntity, BinarySensorEntity):
    """Deprem alarmı — safety: ON = deprem algılandı (ağ doğruladı)."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_name = "Earthquake"

    def __init__(self, entry: GeoShakeConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_earthquake"
        self._attr_is_on = False
        self._cancel_clear: Any = None
        self._off_delay = entry.options.get(CONF_OFF_DELAY, DEFAULT_OFF_DELAY_S)
        # GH3c bölge filtresi: 0 = kapalı. Ev konumu HA yapılandırmasından.
        self._radius_km = entry.options.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)

    def _home(self) -> tuple[float, float]:
        return (self.hass.config.latitude, self.hass.config.longitude)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        data = self._entry.runtime_data

        @callback
        def _on_event(event: GeoShakeEvent) -> None:
            home = self._home()
            # Yarıçap dışındaki olay ALARMI tetiklemez (Last event sensörü yine gösterir).
            if not event_within(event, home[0], home[1], self._radius_km):
                return
            self._attr_is_on = True
            self._attr_extra_state_attributes = event_attributes(event, home)
            self._schedule_clear()
            self.async_write_ha_state()

        data.event_listeners.append(_on_event)
        self.async_on_remove(lambda: data.event_listeners.remove(_on_event))

    def _schedule_clear(self) -> None:
        """off_delay sonra OFF; yeni olayda önceki timer iptal (RESET semantiği)."""
        if self._cancel_clear is not None:
            self._cancel_clear()

        @callback
        def _clear(_now: datetime) -> None:
            self._cancel_clear = None
            self._attr_is_on = False
            self.async_write_ha_state()

        self._cancel_clear = async_call_later(self.hass, self._off_delay, _clear)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._cancel_clear is not None:
            self._cancel_clear()
            self._cancel_clear = None


class ConnectionStatus(GeoShakeEntity, BinarySensorEntity):
    """MQTT bağlantı durumu (diagnostic) — her koşulda görünür kalsın diye available=True."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Connection"

    def __init__(self, entry: GeoShakeConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_connection"

    @property
    def available(self) -> bool:  # bağlantı sensörü kopukken de okunabilir olmalı
        return True

    @property
    def is_on(self) -> bool:
        return self._entry.runtime_data.connected
