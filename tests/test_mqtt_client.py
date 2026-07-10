"""_is_auth_rc testleri — auth tespiti paho/aiomqtt normalizasyonuna bağlı,
regresyon burada yakalanır (review MEDIUM bulgusu).

Not: bu dosya paket import'u kullanır (custom_components.geoshake) → venv'de
homeassistant + aiomqtt kurulu olmalı (README Development bölümü).
"""

from types import SimpleNamespace

import aiomqtt

from custom_components.geoshake.mqtt_client import _is_auth_rc


def code_error(rc) -> aiomqtt.MqttCodeError:
    return aiomqtt.MqttCodeError(rc, "test")


class TestIsAuthRc:
    def test_v311_ham_kodlar_4_5_auth(self):
        # paho normalizasyonu değişirse diye savunma dalı.
        assert _is_auth_rc(code_error(4)) is True
        assert _is_auth_rc(code_error(5)) is True

    def test_v5_reason_code_134_135_auth(self):
        # paho pratikte v3.1.1 CONNACK 4/5'i de bu ReasonCode'lara çevirir:
        # 0x86 BadUserNameOrPassword, 0x87 NotAuthorized.
        assert _is_auth_rc(code_error(SimpleNamespace(value=0x86))) is True
        assert _is_auth_rc(code_error(SimpleNamespace(value=0x87))) is True

    def test_diger_kodlar_auth_degil(self):
        assert _is_auth_rc(code_error(0)) is False
        assert _is_auth_rc(code_error(3)) is False  # server unavailable
        assert _is_auth_rc(code_error(SimpleNamespace(value=0x80))) is False  # generic fail

    def test_rc_none_auth_degil(self):
        assert _is_auth_rc(code_error(None)) is False
