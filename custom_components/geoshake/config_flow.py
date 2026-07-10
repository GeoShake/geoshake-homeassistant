"""GeoShake config flow — UI'dan kurulum (YAML YOK).

GH3c: iki yol —
 · **account** (önerilen): GeoShake hesabı (email/şifre) → /api/ha/credentials
   takası → MQTT credential otomatik gelir (kullanıcı MQTT hiç görmez). Hesap
   şifresi entry'ye YAZILMAZ (tek seferlik takas).
 · **manual** (gelişmiş/eski): broker/port/kullanıcı/şifre elle (gs-readonly vb.).
İki yolda da credential CANLI bağlantıyla doğrulanır (probe_connection).
unique_id = mqtt-username@broker → aynı hesap/credential ikinci kez eklenemez.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiomqtt
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, InvalidAuth, RateLimited, fetch_credentials
from .const import (
    CONF_BROKER,
    CONF_OFF_DELAY,
    CONF_RADIUS_KM,
    DEFAULT_API_BASE,
    DEFAULT_BROKER,
    DEFAULT_OFF_DELAY_S,
    DEFAULT_PORT,
    DEFAULT_RADIUS_KM,
    DOMAIN,
)
from .mqtt_client import AuthFailed, probe_connection

_LOGGER = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 10

ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BROKER, default=DEFAULT_BROKER): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class GeoShakeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Menü: hesapla (önerilen) veya manuel MQTT."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["account", "manual"])

    # ── Yol 1: GeoShake hesabı (GH3c) ────────────────────────────────────────
    async def async_step_account(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                cred = await fetch_credentials(
                    session, DEFAULT_API_BASE, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except RateLimited:
                errors["base"] = "rate_limited"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("GeoShake credential takasinda beklenmeyen hata")
                errors["base"] = "unknown"

            if not errors:
                # Takas edilen MQTT credential'ı CANLI doğrula (uçtan uca kanıt).
                mqtt_data = {
                    CONF_BROKER: cred.broker,
                    CONF_PORT: cred.port,
                    CONF_USERNAME: cred.username,
                    CONF_PASSWORD: cred.password,
                }
                result = await self._finish(mqtt_data, errors)
                if result is not None:
                    return result  # entry oluştu; aksi halde errors dolu → form tekrar

        return self.async_show_form(step_id="account", data_schema=ACCOUNT_SCHEMA, errors=errors)

    # ── Yol 2: manuel MQTT (gelişmiş/eski) ───────────────────────────────────
    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._finish(dict(user_input), errors)
            if result is not None:
                return result

        return self.async_show_form(step_id="manual", data_schema=MANUAL_SCHEMA, errors=errors)

    async def _finish(
        self, mqtt_data: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        """Ortak kapanış: unique_id + canlı MQTT doğrulaması + entry. Hata → None (form tekrar)."""
        await self.async_set_unique_id(f"{mqtt_data[CONF_USERNAME]}@{mqtt_data[CONF_BROKER]}")
        self._abort_if_unique_id_configured()

        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                await probe_connection(
                    mqtt_data[CONF_BROKER],
                    mqtt_data[CONF_PORT],
                    mqtt_data[CONF_USERNAME],
                    mqtt_data[CONF_PASSWORD],
                )
        except AuthFailed:
            errors["base"] = "invalid_auth"
            return None
        except (TimeoutError, OSError, aiomqtt.MqttError):
            errors["base"] = "cannot_connect"
            return None
        except Exception:  # noqa: BLE001
            _LOGGER.exception("GeoShake MQTT dogrulamasinda beklenmeyen hata")
            errors["base"] = "unknown"
            return None

        return self.async_create_entry(title="GeoShake", data=mqtt_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "GeoShakeOptionsFlow":
        return GeoShakeOptionsFlow()


class GeoShakeOptionsFlow(OptionsFlow):
    """Ayarlar: alarm auto-clear süresi + bölge filtresi yarıçapı."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_OFF_DELAY, default=opts.get(CONF_OFF_DELAY, DEFAULT_OFF_DELAY_S)
                ): vol.All(int, vol.Range(min=10, max=3600)),
                # 0 = filtre kapalı (tüm ağ olayları); >0 km = yalnız HA ev konumuna yakın olaylar.
                vol.Required(
                    CONF_RADIUS_KM, default=opts.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)
                ): vol.All(int, vol.Range(min=0, max=20000)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
