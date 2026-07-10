"""GH3c bölge filtresi: haversine_km + event_within (saf matematik, HA'sız)."""

from const import GeoShakeEvent, event_within, haversine_km  # noqa: E402 — yol conftest'te


def ev(lat: float, lon: float) -> GeoShakeEvent:
    return GeoShakeEvent(
        event_id=1, origin_ms=0, lat=lat, lon=lon, n_stations=3,
        intensity_class="hafif", max_pga=0.1,
    )

# Referans noktalar
IST = (41.01, 28.98)   # İstanbul
ANK = (39.93, 32.86)   # Ankara (~350 km)
IZM = (38.42, 27.14)   # İzmir  (~330 km İst'e)


class TestHaversine:
    def test_ayni_nokta_sifir(self):
        assert haversine_km(41.0, 29.0, 41.0, 29.0) == 0.0

    def test_istanbul_ankara_bilinen_mesafe(self):
        d = haversine_km(*IST, *ANK)
        assert 330 <= d <= 370  # ~351 km

    def test_simetrik(self):
        assert haversine_km(*IST, *ANK) == haversine_km(*ANK, *IST)

    def test_ekvator_bir_derece_yaklasik_111km(self):
        d = haversine_km(0, 0, 0, 1)
        assert 110 <= d <= 112


class TestEventWithin:
    def test_yaricap_sifir_filtre_kapali_hep_true(self):
        assert event_within(ev(*ANK), *IST, 0) is True
        assert event_within(ev(-33.0, 151.0), *IST, 0) is True  # Sidney bile

    def test_yaricap_negatif_de_kapali(self):
        assert event_within(ev(*ANK), *IST, -5) is True

    def test_yakin_olay_true_uzak_false(self):
        # İstanbul evi, 100 km yarıçap: Marmara olayı girer, Ankara girmez.
        assert event_within(ev(40.7, 29.1), *IST, 100) is True
        assert event_within(ev(*ANK), *IST, 100) is False

    def test_sinirda_dahil(self):
        d = haversine_km(*IST, *IZM)
        assert event_within(ev(*IZM), *IST, d + 0.1) is True
        assert event_within(ev(*IZM), *IST, d - 0.1) is False
