"""GeoShake MQTT istemcisi — aiomqtt sarmalayıcı (HA'dan bağımsız, test edilebilir).

Sorumluluklar:
 · TLS bağlantı (8883, sistem CA — doğrulama ASLA kapatılmaz) + geoshake/events qos1
 · Mesaj → parse_event → dedup → event_callback (yalnız YENİ ve GEÇERLİ olaylar)
 · Kopunca exponential backoff ile sonsuz yeniden bağlanma (2s→60s)
 · Bağlantı durumu değişince status_callback(bool) — connectivity entity beslenir
Hata felsefesi GH worker ile aynı: hiçbir mesaj/ağ hatası istemciyi ÖLDÜRMEZ;
credential'lar asla loglanmaz.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import Callable

import aiomqtt

from .const import (
    EVENTS_TOPIC,
    DedupRing,
    GeoShakeEvent,
    next_backoff,
    parse_event,
)

_LOGGER = logging.getLogger(__name__)

EventCallback = Callable[[GeoShakeEvent], None]
StatusCallback = Callable[[bool], None]


class AuthFailed(Exception):
    """Broker kimlik doğrulamayı reddetti (yanlış kullanıcı/şifre veya ACL)."""


async def probe_connection(broker: str, port: int, username: str, password: str) -> None:
    """Config flow doğrulaması: bağlan + subscribe dene, sonra kapat.

    Başarısızlıkta ayrıştırılmış hata: AuthFailed (rc=bad auth) / diğer istisnalar
    cannot_connect'e eşlenir. 10sn toplam zaman sınırı ÇAĞIRANDA (asyncio.timeout).
    """
    tls = ssl.create_default_context()  # sistem CA; hostname doğrulaması AÇIK
    try:
        async with aiomqtt.Client(
            hostname=broker, port=port, username=username, password=password, tls_context=tls
        ) as client:
            await client.subscribe(EVENTS_TOPIC, qos=1)
    except aiomqtt.MqttCodeError as e:
        # Kimlik/yetki reddi → AuthFailed (config flow "invalid_auth" gösterir).
        if _is_auth_rc(e):
            raise AuthFailed from e
        raise


def _is_auth_rc(e: aiomqtt.MqttCodeError) -> bool:
    """MQTT dönüş kodu kimlik/yetki hatası mı?

    paho, v3.1.1 CONNACK 4/5'i de ReasonCode 0x86 (BadUserNameOrPassword) /
    0x87 (NotAuthorized) olarak normalize eder → pratikte eşleşme .value 134/135
    üzerinden olur. Ham int 4/5 dalı, paho normalizasyonu değişirse diye savunma.
    """
    rc = getattr(e, "rc", None)
    code = rc if isinstance(rc, int) else getattr(rc, "value", None)
    return code in (4, 5, 0x86, 0x87)


class GeoShakeMqttClient:
    """Uzun ömürlü dinleyici. start() bir asyncio task açar; stop() temiz kapatır."""

    def __init__(
        self,
        broker: str,
        port: int,
        username: str,
        password: str,
        on_event: EventCallback,
        on_status: StatusCallback,
    ) -> None:
        self._broker = broker
        self._port = port
        self._username = username
        self._password = password
        self._on_event = on_event
        self._on_status = on_status
        self._dedup = DedupRing()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        """Dinleme task'ını başlat (idempotent)."""
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        """Task'ı iptal et ve bitmesini bekle (unload/reload yolu)."""
        self._stopping = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        """Bağlan-dinle-kop-yeniden-bağlan döngüsü. Yalnız cancel ile biter."""
        backoff: float | None = None
        tls = ssl.create_default_context()
        while not self._stopping:
            try:
                async with aiomqtt.Client(
                    hostname=self._broker,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                    tls_context=tls,
                ) as client:
                    await client.subscribe(EVENTS_TOPIC, qos=1)
                    backoff = None  # başarılı bağlantı → backoff sıfırla
                    self._safe_status(True)
                    async for message in client.messages:
                        self._handle(bytes(message.payload))  # type: ignore[arg-type]
            except asyncio.CancelledError:
                self._safe_status(False)
                raise
            except Exception as e:  # noqa: BLE001 — ağ/TLS/MQTT: yut, logla, yeniden dene
                self._safe_status(False)
                backoff = next_backoff(backoff)
                # Credential loglanmaz; yalnız hata TİPİ (mesaj şifre içermez ama tipi yeter).
                _LOGGER.warning(
                    "GeoShake MQTT baglantisi koptu (%s); %.0fsn sonra yeniden denenecek",
                    type(e).__name__,
                    backoff,
                )
                await asyncio.sleep(backoff)

    def _handle(self, payload: bytes) -> None:
        """Tek mesaj: parse + dedup + callback. Callback hatası dinleyiciyi öldürmez."""
        event = parse_event(payload)
        if event is None:
            return  # bozuk/eksik mesaj → yoksay (worker ile aynı)
        if self._dedup.seen_before(event.event_id):
            return  # qos1 redelivery → yoksay
        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("GeoShake olay callback hatasi")

    def _safe_status(self, connected: bool) -> None:
        try:
            self._on_status(connected)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("GeoShake durum callback hatasi")
