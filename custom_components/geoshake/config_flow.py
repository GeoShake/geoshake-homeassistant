"""GeoShake config flow — UI'dan kurulum (YAML YOK).

Kullanıcı broker/port/kullanıcı/şifre girer; CANLI bağlantı denemesiyle doğrulanır
(cannot_connect / invalid_auth ayrımı). unique_id = username@broker → aynı hesap
ikinci kez eklenemez. GH3 (Supabase) geldiğinde bu flow'a email/şifre adımı eklenecek.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiomqtt
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .const import (
    CONF_BROKER,
    CONF_OFF_DELAY,
    DEFAULT_BROKER,
    DEFAULT_OFF_DELAY_S,
    DEFAULT_PORT,
    DOMAIN,
)
from .mqtt_client import AuthFailed, probe_connection

_LOGGER = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 10

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BROKER, default=DEFAULT_BROKER): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class GeoShakeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Tek adımlı kurulum: MQTT credential'ları + canlı doğrulama."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # Aynı hesap+broker ikinci kez eklenmesin.
            await self.async_set_unique_id(
                f"{user_input[CONF_USERNAME]}@{user_input[CONF_BROKER]}"
            )
            self._abort_if_unique_id_configured()

            try:
                async with asyncio.timeout(PROBE_TIMEOUT_S):
                    await probe_connection(
                        user_input[CONF_BROKER],
                        user_input[CONF_PORT],
                        user_input[CONF_USERNAME],
                        user_input[CONF_PASSWORD],
                    )
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except (TimeoutError, OSError, aiomqtt.MqttError):
                # Beklenen ağ/TLS/DNS/MQTT hataları → kullanıcıya bağlantı sorunu de.
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 — programlama hatasını MASKELEME: logla, "unknown"
                _LOGGER.exception("GeoShake baglanti dogrulamasinda beklenmeyen hata")
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(title="GeoShake", data=user_input)

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "GeoShakeOptionsFlow":
        return GeoShakeOptionsFlow()


class GeoShakeOptionsFlow(OptionsFlow):
    """Ayarlar: alarm auto-clear süresi (off_delay)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_OFF_DELAY, DEFAULT_OFF_DELAY_S)
        schema = vol.Schema(
            {
                vol.Required(CONF_OFF_DELAY, default=current): vol.All(
                    int, vol.Range(min=10, max=3600)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
