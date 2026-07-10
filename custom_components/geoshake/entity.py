"""Ortak entity tabanı — tek 'GeoShake Network' cihazı altında toplanır."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from . import GeoShakeConfigEntry
from .const import DOMAIN


class GeoShakeEntity(Entity):
    """Taban: device bilgisi + availability (MQTT bağlı mı)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: GeoShakeConfigEntry) -> None:
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="GeoShake Network",
            manufacturer="GeoShake",
            model="Earthquake Early Warning",
            configuration_url="https://map.geoshake.org",
        )

    @property
    def available(self) -> bool:
        """MQTT kopuksa entity 'unavailable' — kullanıcı sorunu hemen görür."""
        return self._entry.runtime_data.connected

    async def async_added_to_hass(self) -> None:
        """Bağlantı durumu değişince availability'yi tazele."""
        data = self._entry.runtime_data

        def _on_status(_connected: bool) -> None:
            self.async_write_ha_state()

        data.status_listeners.append(_on_status)
        self.async_on_remove(lambda: data.status_listeners.remove(_on_status))
