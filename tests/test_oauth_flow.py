from __future__ import annotations

import asyncio
import importlib
import sys
import types

import pytest


def _install_httpx_stub() -> None:
    if "httpx" in sys.modules:
        return

    module = types.ModuleType("httpx")

    class AsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

    module.AsyncClient = AsyncClient
    sys.modules["httpx"] = module


_install_httpx_stub()

twitch = importlib.import_module("core.twitch")
oauth_server = importlib.import_module("core.oauth_server")


def test_auth_url_contains_state(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, object] = {}

    monkeypatch.setattr(
        twitch,
        "load_config",
        lambda: {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "oauth_state": "",
        },
    )
    monkeypatch.setattr(twitch, "save_config", lambda config: saved.update(config))
    monkeypatch.setattr(
        twitch.secrets,
        "token_urlsafe",
        lambda _: "fixed-oauth-state",
    )

    client = twitch.TwitchClient()
    auth_url = client.get_auth_url()

    assert "state=fixed-oauth-state" in auth_url
    assert saved["oauth_state"] == "fixed-oauth-state"


def test_consume_oauth_state_rejects_mismatched_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, object] = {}

    monkeypatch.setattr(
        twitch,
        "load_config",
        lambda: {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "oauth_state": "expected-state",
        },
    )
    monkeypatch.setattr(twitch, "save_config", lambda config: saved.update(config))

    client = twitch.TwitchClient()

    assert client.consume_oauth_state("received-state") is False
    assert saved["oauth_state"] == ""


def test_validate_state_rejects_mismatched_state() -> None:
    assert oauth_server.validate_state("expected", "received") is False


def test_reset_client_closes_previous_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(twitch, "load_config", lambda: {})
    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()
    old_client = client._client
    client.reset_client()

    assert client._client is not old_client
    assert closed == ["closed"]


def test_rebind_client_closes_previous_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(twitch, "load_config", lambda: {})
    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()
    old_client = client._client
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(client.rebind_client())
    finally:
        loop.close()

    assert client._client is not old_client
    assert closed == ["closed"]


def test_wait_for_oauth_code_propagates_bind_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_bind_error(*args: object, **kwargs: object) -> object:
        raise OSError("Address already in use")

    monkeypatch.setattr(oauth_server, "HTTPServer", raise_bind_error)

    with pytest.raises(OSError):
        oauth_server.wait_for_oauth_code()


def test_exchange_code_persists_user_token_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, object] = {}

    monkeypatch.setattr(
        twitch,
        "load_config",
        lambda: {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "access_token": "",
            "refresh_token": "",
            "token_expires_at": 0,
            "token_type": "app",
        },
    )
    monkeypatch.setattr(twitch, "save_config", lambda config: saved.update(config))

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "access_token": "user-access-token",
                "refresh_token": "user-refresh-token",
                "expires_in": 3600,
            }

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()
    loop = __import__("asyncio").new_event_loop()
    try:
        token_data = loop.run_until_complete(client.exchange_code("oauth-code"))
    finally:
        loop.run_until_complete(client.close())
        loop.close()

    assert token_data["access_token"] == "user-access-token"
    assert saved["access_token"] == "user-access-token"
    assert saved["refresh_token"] == "user-refresh-token"
    assert saved["token_type"] == "user"
    assert saved["token_expires_at"] > 0


def test_get_reuses_single_user_token_refresh_across_concurrent_401s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "access_token": "stale-token",
        "refresh_token": "refresh-token",
        "token_expires_at": 9999999999,
        "token_type": "user",
    }

    class FakeResponse:
        def __init__(
            self,
            status_code: int,
            payload: dict[str, object],
            *,
            text: str = "",
        ) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = text
            self.headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self) -> dict[str, object]:
            return self._payload

    monkeypatch.setattr(twitch, "load_config", lambda: dict(persisted))
    monkeypatch.setattr(twitch, "save_config", lambda config: persisted.update(config))

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._stale_started = 0
            self._release_stale = asyncio.Event()

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            params: object = None,
        ) -> FakeResponse:
            token = headers["Authorization"].split()[1]
            if token == "stale-token":
                self._stale_started += 1
                if self._stale_started == 2:
                    self._release_stale.set()
                await self._release_stale.wait()
                return FakeResponse(401, {"error": "Unauthorized"}, text="unauthorized")
            return FakeResponse(200, {"data": [{"id": "1"}]})

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()

    async def fake_ensure_token() -> str:
        return "stale-token"

    refresh_calls = 0

    async def fake_refresh_user_token() -> str:
        nonlocal refresh_calls
        refresh_calls += 1
        persisted["access_token"] = "fresh-user-token"
        persisted["token_expires_at"] = 9999999999
        return "fresh-user-token"

    client._ensure_token = fake_ensure_token  # type: ignore[method-assign]
    client.refresh_user_token = fake_refresh_user_token  # type: ignore[method-assign]

    async def run_pair() -> list[dict[str, object]]:
        return await asyncio.gather(
            client._get("/users"),
            client._get("/users"),
        )

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(run_pair())
    finally:
        loop.run_until_complete(client.close())
        loop.close()

    assert result == [{"data": [{"id": "1"}]}, {"data": [{"id": "1"}]}]
    assert refresh_calls == 1


def test_get_reuses_single_app_token_refresh_across_concurrent_401s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "access_token": "stale-token",
        "refresh_token": "",
        "token_expires_at": 9999999999,
        "token_type": "app",
    }

    class FakeResponse:
        def __init__(
            self,
            status_code: int,
            payload: dict[str, object],
            *,
            text: str = "",
        ) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = text
            self.headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self) -> dict[str, object]:
            return self._payload

    monkeypatch.setattr(twitch, "load_config", lambda: dict(persisted))
    monkeypatch.setattr(twitch, "save_config", lambda config: persisted.update(config))

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._stale_started = 0
            self._release_stale = asyncio.Event()

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            params: object = None,
        ) -> FakeResponse:
            token = headers["Authorization"].split()[1]
            if token == "stale-token":
                self._stale_started += 1
                if self._stale_started == 2:
                    self._release_stale.set()
                await self._release_stale.wait()
                return FakeResponse(401, {"error": "Unauthorized"}, text="unauthorized")
            return FakeResponse(200, {"data": [{"id": "1"}]})

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()

    async def fake_ensure_token() -> str:
        return "stale-token"

    refresh_calls = 0

    async def fake_refresh_app_token() -> str:
        nonlocal refresh_calls
        refresh_calls += 1
        persisted["access_token"] = "fresh-app-token"
        persisted["token_expires_at"] = 9999999999
        return "fresh-app-token"

    client._ensure_token = fake_ensure_token  # type: ignore[method-assign]
    client._refresh_app_token = fake_refresh_app_token  # type: ignore[method-assign]

    async def run_pair() -> list[dict[str, object]]:
        return await asyncio.gather(
            client._get("/users"),
            client._get("/users"),
        )

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(run_pair())
    finally:
        loop.run_until_complete(client.close())
        loop.close()

    assert result == [{"data": [{"id": "1"}]}, {"data": [{"id": "1"}]}]
    assert refresh_calls == 1


def test_get_waits_for_known_rate_limit_window_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "access_token": "token",
        "refresh_token": "",
        "token_expires_at": 9999999999,
        "token_type": "app",
    }
    state = {"now": 100.0}
    sleep_calls: list[float] = []
    call_times: list[float] = []

    class FakeResponse:
        status_code = 200
        headers: dict[str, str] = {}
        text = ""

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"data": [{"id": "1"}]}

    monkeypatch.setattr(twitch, "load_config", lambda: dict(persisted))
    monkeypatch.setattr(twitch, "save_config", lambda config: persisted.update(config))
    monkeypatch.setattr(twitch.time, "time", lambda: state["now"])

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        state["now"] += delay

    monkeypatch.setattr(twitch.asyncio, "sleep", fake_sleep)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            params: object = None,
        ) -> FakeResponse:
            call_times.append(state["now"])
            return FakeResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()
    client._rate_limit_reset_at = 105.0

    async def fake_ensure_token() -> str:
        return "token"

    client._ensure_token = fake_ensure_token  # type: ignore[method-assign]

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(client._get("/users"))
    finally:
        loop.run_until_complete(client.close())
        loop.close()

    assert result == {"data": [{"id": "1"}]}
    assert sleep_calls == [5.0]
    assert call_times == [105.0]


def test_concurrent_gets_wait_for_shared_rate_limit_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "access_token": "token",
        "refresh_token": "",
        "token_expires_at": 9999999999,
        "token_type": "app",
    }
    state = {"now": 100.0}
    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    class FakeResponse:
        def __init__(
            self,
            status_code: int,
            payload: dict[str, object],
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers = headers or {}
            self.text = ""

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self) -> dict[str, object]:
            return self._payload

    monkeypatch.setattr(twitch, "load_config", lambda: dict(persisted))
    monkeypatch.setattr(twitch, "save_config", lambda config: persisted.update(config))
    monkeypatch.setattr(twitch.time, "time", lambda: state["now"])

    sleep_started = asyncio.Event()
    release_sleep = asyncio.Event()

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        sleep_started.set()
        await release_sleep.wait()
        state["now"] += delay

    monkeypatch.setattr(twitch.asyncio, "sleep", fake_sleep)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.call_times: list[float] = []

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            params: object = None,
        ) -> FakeResponse:
            self.call_times.append(state["now"])
            if len(self.call_times) == 1:
                return FakeResponse(
                    429,
                    {"error": "rate limited"},
                    headers={"Ratelimit-Reset": "105"},
                )
            return FakeResponse(200, {"data": [{"id": str(len(self.call_times))}]})

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(twitch.httpx, "AsyncClient", FakeAsyncClient)

    client = twitch.TwitchClient()
    http_client = client._client

    async def fake_ensure_token() -> str:
        return "token"

    client._ensure_token = fake_ensure_token  # type: ignore[method-assign]

    async def run_pair() -> tuple[int, list[dict[str, object]]]:
        first = asyncio.create_task(client._get("/users"))
        await sleep_started.wait()
        second = asyncio.create_task(client._get("/users"))
        await real_sleep(0)
        calls_before_release = len(http_client.call_times)
        release_sleep.set()
        result = await asyncio.gather(first, second)
        return calls_before_release, result

    loop = asyncio.new_event_loop()
    try:
        calls_before_release, result = loop.run_until_complete(run_pair())
    finally:
        loop.run_until_complete(client.close())
        loop.close()

    assert calls_before_release == 1
    assert result == [{"data": [{"id": "2"}]}, {"data": [{"id": "3"}]}]
    assert sleep_calls == [5.0]
