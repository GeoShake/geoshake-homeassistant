"""GH3c config flow testleri — özellikle KRİTİK SIRA regression'ı:

Account yolunda dedup (unique_id + abort) MINT'TEN ÖNCE çalışmalı; aksi halde
"already_configured" abort'u bile sunucuda rotate tetikler ve MEVCUT kurulumun
credential'ını sessizce geçersizleştirir (review Critical-1).

HA framework parçaları (async_set_unique_id vb.) monkeypatch'lenir — amaç
flow'un KENDİ mantığının sırası/eşlemesi, framework davranışı değil.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.geoshake import config_flow as cf
from custom_components.geoshake.api import InvalidAuth, MintedCredentials, RateLimited


CRED = MintedCredentials(broker="mqtt.geoshake.org", port=8883, username="gs-cust-abc", password="mqtt-pw")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def make_flow(calls: list, abort_on_unique: bool = False):
    """Flow'u framework'süz kur: unique_id/abort kayıt altına alınır."""
    flow = cf.GeoShakeConfigFlow()
    flow.hass = SimpleNamespace()  # async_get_clientsession patch'lenir; hass kullanılmaz
    flow.flow_id = "test-flow"
    flow.context = {}

    async def fake_set_unique_id(uid):
        calls.append(("unique_id", uid))

    def fake_abort_if_configured():
        calls.append(("abort_check",))
        if abort_on_unique:
            raise AbortFlow("already_configured")

    flow.async_set_unique_id = fake_set_unique_id
    flow._abort_if_unique_id_configured = fake_abort_if_configured
    return flow


class TestAccountStep:
    def test_KRITIK_dedup_mintten_once(self):
        """Re-add: abort MINT'TEN ÖNCE — fetch_credentials HİÇ çağrılmamalı."""
        calls: list = []
        flow = make_flow(calls, abort_on_unique=True)
        fetch = AsyncMock(return_value=CRED)
        with patch.object(cf, "fetch_credentials", fetch), patch.object(
            cf, "async_get_clientsession", lambda hass: object()
        ):
            with pytest.raises(AbortFlow):
                run(flow.async_step_account({"email": " User@X.co ", "password": "acct-pw"}))
        assert fetch.await_count == 0  # rotate yan etkisi TETİKLENMEDİ
        assert calls[0] == ("unique_id", "user@x.co")  # normalize email, mint'ten önce
        assert calls[1] == ("abort_check",)

    def test_basarili_kurulum_yalniz_mqtt_cred_saklanir(self):
        calls: list = []
        flow = make_flow(calls)
        fetch = AsyncMock(return_value=CRED)
        probe = AsyncMock(return_value=None)
        with patch.object(cf, "fetch_credentials", fetch), patch.object(
            cf, "probe_connection", probe
        ), patch.object(cf, "async_get_clientsession", lambda hass: object()):
            result = run(flow.async_step_account({"email": "a@b.co", "password": "acct-sifre"}))

        assert result["type"].value == "create_entry"
        # Entry'de HESAP ŞİFRESİ YOK — yalnız takas edilen MQTT credential'ı.
        assert result["data"] == {
            "broker": "mqtt.geoshake.org",
            "port": 8883,
            "username": "gs-cust-abc",
            "password": "mqtt-pw",
        }
        assert "acct-sifre" not in str(result["data"])
        # unique_id yalnız BİR kez (email) set edildi — _finish tekrar set etmedi.
        assert [c for c in calls if c[0] == "unique_id"] == [("unique_id", "a@b.co")]
        probe.assert_awaited_once()  # mint edilen credential canlı doğrulandı

    @pytest.mark.parametrize(
        ("exc", "expected"),
        [(InvalidAuth(), "invalid_auth"), (RateLimited(), "rate_limited")],
    )
    def test_hata_eslemeleri_form_tekrar(self, exc, expected):
        calls: list = []
        flow = make_flow(calls)
        fetch = AsyncMock(side_effect=exc)
        with patch.object(cf, "fetch_credentials", fetch), patch.object(
            cf, "async_get_clientsession", lambda hass: object()
        ):
            result = run(flow.async_step_account({"email": "a@b.co", "password": "pw"}))
        assert result["type"].value == "form"
        assert result["errors"]["base"] == expected

    def test_probe_fail_form_tekrar_entry_yok(self):
        calls: list = []
        flow = make_flow(calls)
        fetch = AsyncMock(return_value=CRED)
        probe = AsyncMock(side_effect=cf.AuthFailed())
        with patch.object(cf, "fetch_credentials", fetch), patch.object(
            cf, "probe_connection", probe
        ), patch.object(cf, "async_get_clientsession", lambda hass: object()):
            result = run(flow.async_step_account({"email": "a@b.co", "password": "pw"}))
        assert result["type"].value == "form"
        assert result["errors"]["base"] == "invalid_auth"


class TestManualStep:
    def test_manuel_yol_username_broker_unique_id(self):
        calls: list = []
        flow = make_flow(calls)
        probe = AsyncMock(return_value=None)
        data = {"broker": "mqtt.geoshake.org", "port": 8883, "username": "gs-readonly", "password": "pw"}
        with patch.object(cf, "probe_connection", probe):
            result = run(flow.async_step_manual(dict(data)))
        assert result["type"].value == "create_entry"
        assert ("unique_id", "gs-readonly@mqtt.geoshake.org") in calls
