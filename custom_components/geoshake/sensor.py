"""GeoShake sensörleri — son olay zamanı (timestamp) + olay öznitelikleri."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GeoShakeConfigEntry
from .binary_sensor import event_attributes
from .const import GeoShakeEvent
from .entity import GeoShakeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoShakeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([LastEventSensor(entry)])


class LastEventSensor(GeoShakeEntity, SensorEntity):
    """Son doğrulanmış deprem olayının origin zamanı; detaylar özniteliklerde."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last event"

    def __init__(self, entry: GeoShakeConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_last_event"
        # Entry kurulumundan önce gelen son olay varsa (reload) onu göster.
        last = entry.runtime_data.last_event
        if last is not None:
            self._apply(last)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        data = self._entry.runtime_data

        @callback
        def _on_event(event: GeoShakeEvent) -> None:
            self._apply(event)
            self.async_write_ha_state()

        data.event_listeners.append(_on_event)
        self.async_on_remove(lambda: data.event_listeners.remove(_on_event))

    def _apply(self, event: GeoShakeEvent) -> None:
        self._attr_native_value = datetime.fromtimestamp(event.origin_ms / 1000, tz=timezone.utc)
        self._attr_extra_state_attributes = event_attributes(event)
