"""GeoShake sabitleri + SAF yardımcılar.

Bu modül Home Assistant IMPORT ETMEZ — parse/dedup mantığı düz pytest ile test
edilir (GH worker'daki parseEventId/dedup disiplininin Python karşılığı).
Payload sözleşmesi: geoshake/events EventPacket JSON —
{v, event_id, originMs, lat, lon, nStations, intensityClass, maxPga, rmsResidual}
"""

from __future__ import annotations

import json
from dataclasses import dataclass

DOMAIN = "geoshake"

DEFAULT_BROKER = "mqtt.geoshake.org"
DEFAULT_PORT = 8883
EVENTS_TOPIC = "geoshake/events"

CONF_BROKER = "broker"
CONF_OFF_DELAY = "off_delay"

# Alarm semantiği GH worker ile AYNI: 120sn yeni olay yoksa normale dön.
DEFAULT_OFF_DELAY_S = 120
# qos1 redelivery dedup halkası kapasitesi (worker DEDUP_MAX ile aynı).
DEDUP_MAX = 32

# Yeniden bağlanma backoff'u: 2s'den başla, her denemede ikiye katla, 60s'de dur.
RECONNECT_MIN_S = 2.0
RECONNECT_MAX_S = 60.0


@dataclass(frozen=True)
class GeoShakeEvent:
    """Doğrulanmış deprem olayı (öznitelikler entity'lere yansır)."""

    event_id: int
    origin_ms: int
    lat: float
    lon: float
    n_stations: int
    intensity_class: str
    max_pga: float


def _finite_number(v: object) -> float | None:
    """Sonlu sayı ise float döndür; bool SAYI DEĞİL (True==1 tuzağı)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    # NaN/Inf reddet: NaN != NaN
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _finite_int(v: object) -> int | None:
    """TAM sayı ise int döndür — 42.9 gibi kesirli değeri SESSİZCE KIRPMA, reddet."""
    f = _finite_number(v)
    if f is None or not float(f).is_integer():
        return None
    return int(f)


def parse_event(payload: bytes | str) -> GeoShakeEvent | None:
    """Olay mesajını savunmacı parse et; geçersizse None (çağıran yoksayar).

    Bozuk JSON / eksik alan / yanlış tip worker'ı asla düşürmemeli — GH worker
    parseEventId ile aynı sözleşme, ama entity öznitelikleri için tüm alanlar.
    """
    try:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        obj = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None

    event_id = _finite_int(obj.get("event_id"))
    origin_ms = _finite_int(obj.get("originMs"))
    lat = _finite_number(obj.get("lat"))
    lon = _finite_number(obj.get("lon"))
    n_stations = _finite_int(obj.get("nStations"))
    max_pga = _finite_number(obj.get("maxPga"))
    intensity = obj.get("intensityClass")

    # event_id zorunlu (dedup anahtarı); diğer zorunlular: origin/koordinat/istasyon.
    if event_id is None or origin_ms is None or lat is None or lon is None:
        return None
    if n_stations is None or max_pga is None or not isinstance(intensity, str) or not intensity:
        return None
    # Koordinat aralığı: geçersiz konum haritada/öznitelikte saçmalık üretmesin.
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None

    return GeoShakeEvent(
        event_id=event_id,
        origin_ms=origin_ms,
        lat=lat,
        lon=lon,
        n_stations=n_stations,
        intensity_class=intensity,
        max_pga=max_pga,
    )


class DedupRing:
    """Son N event_id halkası — qos1 redelivery tekrarını yut (worker ile aynı)."""

    def __init__(self, capacity: int = DEDUP_MAX) -> None:
        self._capacity = capacity
        self._seen: set[int] = set()
        self._order: list[int] = []

    def seen_before(self, event_id: int) -> bool:
        """id daha önce görüldüyse True; görülmediyse kaydet ve False."""
        if event_id in self._seen:
            return True
        self._seen.add(event_id)
        self._order.append(event_id)
        if len(self._order) > self._capacity:
            oldest = self._order.pop(0)
            self._seen.discard(oldest)
        return False


def next_backoff(current: float | None) -> float:
    """Yeniden bağlanma gecikmesi: None→MIN; sonra 2x, MAX'ta doyur."""
    if current is None:
        return RECONNECT_MIN_S
    return min(current * 2, RECONNECT_MAX_S)
