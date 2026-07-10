"""GeoShake hesap → MQTT credential takası (GH3b /api/ha/credentials istemcisi).

HA import'u YOK — session dışarıdan verilir (aiohttp arayüzü), stub'la test edilir.
Hesap ŞİFRESİ yalnız bu tek istekte kullanılır; entegrasyon SAKLAMAZ (entry'ye
yalnız dönen MQTT credential'ı yazılır). Şifre/credential ASLA loglanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EXCHANGE_TIMEOUT_S = 15


class InvalidAuth(Exception):
    """GeoShake hesabı reddetti (401 — yanlış email/şifre)."""


class RateLimited(Exception):
    """429 — çok fazla deneme; kullanıcı biraz bekleyip tekrar denemeli."""


class CannotConnect(Exception):
    """Ağ/5xx/bozuk yanıt — sunucuya ulaşılamadı ya da güvenilir yanıt alınamadı."""


@dataclass(frozen=True)
class MintedCredentials:
    broker: str
    port: int
    username: str
    password: str


async def fetch_credentials(session: Any, api_base: str, email: str, password: str) -> MintedCredentials:
    """Hesapla MQTT credential'ı takas et.

    session: aiohttp.ClientSession (HA `async_get_clientsession`); testte stub.
    401 → InvalidAuth, 429 → RateLimited, diğer HTTP/ağ/şekil hatası → CannotConnect.
    """
    url = api_base.rstrip("/") + "/api/ha/credentials"
    try:
        async with session.post(
            url,
            json={"email": email.strip(), "password": password},
            timeout=EXCHANGE_TIMEOUT_S,
        ) as res:
            if res.status == 401:
                raise InvalidAuth
            if res.status == 429:
                raise RateLimited
            if res.status != 200:
                raise CannotConnect(f"HTTP {res.status}")
            body = await res.json()
    except (InvalidAuth, RateLimited, CannotConnect):
        raise
    except Exception as e:  # noqa: BLE001 — ağ/DNS/TLS/timeout/bozuk-json
        raise CannotConnect(type(e).__name__) from e

    # Savunmacı şekil doğrulama — eksik alanla yarım entry YAZILMAZ.
    broker, port = body.get("broker"), body.get("port")
    username, mqtt_password = body.get("username"), body.get("password")
    if (
        not isinstance(broker, str) or not broker
        or not isinstance(port, int)
        or not isinstance(username, str) or not username
        or not isinstance(mqtt_password, str) or not mqtt_password
    ):
        raise CannotConnect("eksik alan")

    return MintedCredentials(broker=broker, port=port, username=username, password=mqtt_password)
