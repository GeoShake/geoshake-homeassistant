"""GH3c api.fetch_credentials: hesap → MQTT credential takası (stub session, ağ YOK)."""

import asyncio

import pytest

from custom_components.geoshake.api import (
    CannotConnect,
    InvalidAuth,
    MintedCredentials,
    RateLimited,
    fetch_credentials,
)

VALID = {"broker": "mqtt.geoshake.org", "port": 8883, "username": "gs-cust-abc", "password": "pw123"}


class StubResponse:
    def __init__(self, status: int, body):
        self.status = status
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class StubSession:
    """aiohttp.ClientSession.post async-context sözleşmesinin minimal taklidi."""

    def __init__(self, response: StubResponse | Exception):
        self._response = response
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        response = self._response

        class _Ctx:
            async def __aenter__(self):
                if isinstance(response, Exception):
                    raise response
                return response

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class TestFetchCredentials:
    def test_mutlu_yol_dogru_istek_ve_donus(self):
        s = StubSession(StubResponse(200, VALID))
        cred = run(fetch_credentials(s, "https://map.geoshake.org", " User@X.co ", "acct-pw"))
        assert cred == MintedCredentials(**VALID)
        url, kwargs = s.calls[0]
        assert url == "https://map.geoshake.org/api/ha/credentials"
        assert kwargs["json"] == {"email": "User@X.co", "password": "acct-pw"}  # trim edilir, case sunucuda

    def test_api_base_sondaki_slash_normalize(self):
        s = StubSession(StubResponse(200, VALID))
        run(fetch_credentials(s, "https://map.geoshake.org/", "a@b.co", "pw"))
        assert s.calls[0][0] == "https://map.geoshake.org/api/ha/credentials"

    def test_401_invalid_auth(self):
        with pytest.raises(InvalidAuth):
            run(fetch_credentials(StubSession(StubResponse(401, {})), "https://x", "a@b.co", "pw"))

    def test_429_rate_limited(self):
        with pytest.raises(RateLimited):
            run(fetch_credentials(StubSession(StubResponse(429, {})), "https://x", "a@b.co", "pw"))

    def test_5xx_cannot_connect(self):
        with pytest.raises(CannotConnect):
            run(fetch_credentials(StubSession(StubResponse(503, {})), "https://x", "a@b.co", "pw"))

    def test_ag_hatasi_cannot_connect(self):
        with pytest.raises(CannotConnect):
            run(fetch_credentials(StubSession(OSError("conn refused")), "https://x", "a@b.co", "pw"))

    def test_bozuk_json_cannot_connect(self):
        s = StubSession(StubResponse(200, ValueError("bad json")))
        with pytest.raises(CannotConnect):
            run(fetch_credentials(s, "https://x", "a@b.co", "pw"))

    def test_eksik_alan_cannot_connect(self):
        for missing in ("broker", "port", "username", "password"):
            body = {k: v for k, v in VALID.items() if k != missing}
            with pytest.raises(CannotConnect):
                run(fetch_credentials(StubSession(StubResponse(200, body)), "https://x", "a@b.co", "pw"))

    def test_port_string_reddedilir(self):
        body = {**VALID, "port": "8883"}
        with pytest.raises(CannotConnect):
            run(fetch_credentials(StubSession(StubResponse(200, body)), "https://x", "a@b.co", "pw"))
