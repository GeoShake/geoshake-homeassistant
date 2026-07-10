"""Saf çekirdek testleri: parse_event + DedupRing + next_backoff.

HA'sız çalışır (const.py Home Assistant import etmez) — düz pytest.
Payload sözleşmesi: geoshake/events EventPacket JSON (assoc üretir).
"""

import json

from const import (  # noqa: E402 — yol conftest.py'de kurulur
    DEDUP_MAX,
    RECONNECT_MAX_S,
    RECONNECT_MIN_S,
    DedupRing,
    next_backoff,
    parse_event,
)


def valid_payload(**overrides):
    base = {
        "v": 1,
        "event_id": 42,
        "originMs": 1752130000000,
        "lat": 40.71,
        "lon": 29.05,
        "nStations": 3,
        "intensityClass": "moderate",
        "maxPga": 0.12,
        "rmsResidual": 0.4,
    }
    base.update(overrides)
    return json.dumps(base).encode("utf-8")


class TestParseEvent:
    def test_gecerli_payload_tum_alanlar(self):
        e = parse_event(valid_payload())
        assert e is not None
        assert e.event_id == 42
        assert e.origin_ms == 1752130000000
        assert e.lat == 40.71 and e.lon == 29.05
        assert e.n_stations == 3
        assert e.intensity_class == "moderate"
        assert e.max_pga == 0.12

    def test_str_payload_da_kabul(self):
        assert parse_event(valid_payload().decode()) is not None

    def test_bozuk_json_none(self):
        assert parse_event(b"{bozuk json") is None

    def test_json_ama_dict_degil_none(self):
        assert parse_event(b"[1,2,3]") is None
        assert parse_event(b'"str"') is None

    def test_event_id_yok_none(self):
        p = json.loads(valid_payload())
        del p["event_id"]
        assert parse_event(json.dumps(p)) is None

    def test_event_id_string_none(self):
        assert parse_event(valid_payload(event_id="42")) is None

    def test_event_id_bool_none(self):
        # bool int alt-tipi — True'yu 1 sanma tuzağı kapalı olmalı.
        assert parse_event(valid_payload(event_id=True)) is None

    def test_nan_koordinat_none(self):
        # json.dumps NaN'i "NaN" yazar (JS tarafı üretmez ama savunma).
        raw = valid_payload().decode().replace("40.71", "NaN")
        assert parse_event(raw) is None

    def test_infinity_none(self):
        raw = valid_payload().decode().replace("40.71", "Infinity")
        assert parse_event(raw) is None

    def test_kesirli_event_id_none(self):
        # int alanlar SESSİZCE KIRPILMAZ — 42.9 reddedilir.
        assert parse_event(valid_payload(event_id=42.9)) is None
        assert parse_event(valid_payload(nStations=2.5)) is None

    def test_tam_float_event_id_kabul(self):
        # 42.0 tam sayı — kabul edilir (JSON number ayrımı yapmaz).
        e = parse_event(valid_payload(event_id=42.0))
        assert e is not None and e.event_id == 42

    def test_koordinat_araligi_disi_none(self):
        assert parse_event(valid_payload(lat=91)) is None
        assert parse_event(valid_payload(lat=-91)) is None
        assert parse_event(valid_payload(lon=181)) is None
        assert parse_event(valid_payload(lon=-181)) is None

    def test_bos_intensity_class_none(self):
        assert parse_event(valid_payload(intensityClass="")) is None

    def test_intensity_class_sayi_none(self):
        assert parse_event(valid_payload(intensityClass=3)) is None

    def test_eksik_zorunlu_alanlar_none(self):
        for field in ("originMs", "lat", "lon", "nStations", "maxPga"):
            p = json.loads(valid_payload())
            del p[field]
            assert parse_event(json.dumps(p)) is None, field

    def test_fazladan_alan_sorun_degil(self):
        assert parse_event(valid_payload(extra="ignored")) is not None

    def test_gecersiz_utf8_none(self):
        assert parse_event(b"\xff\xfe{") is None


class TestDedupRing:
    def test_ilk_gorus_false_tekrar_true(self):
        ring = DedupRing()
        assert ring.seen_before(7) is False
        assert ring.seen_before(7) is True

    def test_farkli_idler_bagimsiz(self):
        ring = DedupRing()
        assert ring.seen_before(1) is False
        assert ring.seen_before(2) is False
        assert ring.seen_before(1) is True

    def test_kapasite_asiminda_en_eski_tahliye(self):
        ring = DedupRing(capacity=3)
        for i in (1, 2, 3):
            ring.seen_before(i)
        ring.seen_before(4)  # 1 tahliye edilir
        assert ring.seen_before(1) is False  # yeniden "yeni" sayılır
        assert ring.seen_before(4) is True

    def test_varsayilan_kapasite_worker_ile_ayni(self):
        assert DEDUP_MAX == 32


class TestNextBackoff:
    def test_ilk_deneme_min(self):
        assert next_backoff(None) == RECONNECT_MIN_S

    def test_her_denemede_iki_kat(self):
        assert next_backoff(2.0) == 4.0
        assert next_backoff(16.0) == 32.0

    def test_max_ta_doyar(self):
        assert next_backoff(RECONNECT_MAX_S) == RECONNECT_MAX_S
        assert next_backoff(59.0) == RECONNECT_MAX_S
