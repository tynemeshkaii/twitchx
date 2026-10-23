from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from core.platforms.twitch import OAUTH_SCOPE, TwitchClient


class TestOAuthScopeIncludesModeration:
    def test_scope_contains_moderator_manage_chat_settings(self) -> None:
        assert "moderator:manage:chat_settings" in OAUTH_SCOPE

    def test_scope_preserves_existing_scopes(self) -> None:
        assert "user:read:follows" in OAUTH_SCOPE
        assert "chat:read" in OAUTH_SCOPE
        assert "chat:edit" in OAUTH_SCOPE


class TestSetChatSettings:
    def _make_client(
        self,
        patch_response: dict[str, Any] | None = None,
    ) -> TwitchClient:
        client = TwitchClient()
        if patch_response is not None:

            async def fake_patch(
                url: str,
                *,
                headers: dict[str, str] | None = None,
                params: Any = None,
                json: Any = None,
            ) -> MagicMock:
                resp = MagicMock()
                resp.status_code = 200
                resp.raise_for_status = MagicMock()
                resp.json = MagicMock(return_value=patch_response)
                fake_patch.last_url = url  # type: ignore[attr-defined]
                fake_patch.last_headers = headers  # type: ignore[attr-defined]
                fake_patch.last_params = params  # type: ignore[attr-defined]
                fake_patch.last_body = json  # type: ignore[attr-defined]
                return resp

            mock_client = MagicMock()
            mock_client.patch = fake_patch
            client._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

            async def fake_ensure_token() -> str:
                return "test-token"

            client._ensure_token = fake_ensure_token  # type: ignore[method-assign]

            client._reload_config()
            tc = client._platform_config()
            tc["client_id"] = "test-client-id"

        return client

    def test_emote_only_mode(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": False,
                        "slow_mode_wait_time": None,
                        "emote_mode": True,
                        "subscriber_mode": False,
                        "follower_mode": False,
                        "follower_mode_duration": None,
                    }
                ]
            }
        )

        async def run() -> None:
            result = await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                emote_mode=True,
            )
            assert result["emote_mode"] is True
            assert result["broadcaster_id"] == "111"

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()

    def test_slow_mode_with_duration(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": True,
                        "slow_mode_wait_time": 30,
                        "emote_mode": False,
                        "subscriber_mode": False,
                        "follower_mode": False,
                        "follower_mode_duration": None,
                    }
                ]
            }
        )

        async def run() -> None:
            result = await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                slow_mode=True,
                slow_mode_wait_time=30,
            )
            assert result["slow_mode"] is True
            assert result["slow_mode_wait_time"] == 30

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()

    def test_sends_correct_params_and_body(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": True,
                        "slow_mode_wait_time": 10,
                        "emote_mode": True,
                        "subscriber_mode": False,
                        "follower_mode": False,
                        "follower_mode_duration": None,
                    }
                ]
            }
        )

        async def run() -> None:
            await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                slow_mode=True,
                slow_mode_wait_time=10,
                emote_mode=True,
            )
            mock_client = client._get_client()
            patch_fn = mock_client.patch
            assert patch_fn.last_url == "https://api.twitch.tv/helix/chat/settings"  # type: ignore[attr-defined]
            assert patch_fn.last_params == {  # type: ignore[attr-defined]
                "broadcaster_id": "111",
                "moderator_id": "222",
            }
            body = patch_fn.last_body  # type: ignore[attr-defined]
            assert body["slow_mode"] is True
            assert body["slow_mode_wait_time"] == 10
            assert body["emote_mode"] is True

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()

    def test_omits_none_params_from_body(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": False,
                        "slow_mode_wait_time": None,
                        "emote_mode": True,
                        "subscriber_mode": False,
                        "follower_mode": False,
                        "follower_mode_duration": None,
                    }
                ]
            }
        )

        async def run() -> None:
            await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                emote_mode=True,
            )
            mock_client = client._get_client()
            patch_fn = mock_client.patch
            body = patch_fn.last_body  # type: ignore[attr-defined]
            assert "slow_mode" not in body
            assert "slow_mode_wait_time" not in body
            assert "subscriber_mode" not in body
            assert "follower_mode" not in body
            assert "follower_mode_duration" not in body
            assert body["emote_mode"] is True

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()

    def test_sends_auth_headers(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": False,
                        "slow_mode_wait_time": None,
                        "emote_mode": False,
                        "subscriber_mode": False,
                        "follower_mode": False,
                        "follower_mode_duration": None,
                    }
                ]
            }
        )

        async def run() -> None:
            await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                emote_mode=False,
            )
            mock_client = client._get_client()
            patch_fn = mock_client.patch
            headers = patch_fn.last_headers  # type: ignore[attr-defined]
            assert headers["Authorization"] == "Bearer test-token"
            assert headers["Client-Id"] == "test-client-id"
            assert headers["Content-Type"] == "application/json"

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()

    def test_follower_mode_with_duration(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": False,
                        "slow_mode_wait_time": None,
                        "emote_mode": False,
                        "subscriber_mode": False,
                        "follower_mode": True,
                        "follower_mode_duration": 600,
                    }
                ]
            }
        )

        async def run() -> None:
            result = await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                follower_mode=True,
                follower_mode_duration=600,
            )
            assert result["follower_mode"] is True
            assert result["follower_mode_duration"] == 600

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()

    def test_subscriber_mode(self) -> None:
        client = self._make_client(
            patch_response={
                "data": [
                    {
                        "broadcaster_id": "111",
                        "moderator_id": "222",
                        "slow_mode": False,
                        "slow_mode_wait_time": None,
                        "emote_mode": False,
                        "subscriber_mode": True,
                        "follower_mode": False,
                        "follower_mode_duration": None,
                    }
                ]
            }
        )

        async def run() -> None:
            result = await client.set_chat_settings(
                broadcaster_id="111",
                moderator_id="222",
                subscriber_mode=True,
            )
            assert result["subscriber_mode"] is True

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()


class TestSetChatSettingsEmptyResponse:
    def test_empty_data_list_returns_empty_dict(self) -> None:
        client = TestSetChatSettings()._make_client(patch_response={"data": []})

        async def run() -> dict[str, Any]:
            return await client.set_chat_settings(
                broadcaster_id="111", moderator_id="111", emote_mode=True
            )

        loop = asyncio.new_event_loop()
        try:
            assert loop.run_until_complete(run()) == {}
        finally:
            loop.run_until_complete(client.close_loop_resources())
            loop.close()


class TestSetChatModeApi:
    @staticmethod
    def _api(monkeypatch: Any, settings_result: Any) -> tuple[Any, list[str], Any]:
        from unittest.mock import AsyncMock

        from core.storage import update_config
        from ui.api import TwitchXApi
        from ui.api.streams import WatchTarget

        def _login(cfg: dict) -> None:
            cfg["platforms"]["twitch"]["user_id"] = "111"

        update_config(_login)
        api = TwitchXApi()
        api._watching = WatchTarget("twitch", "me")
        calls: list[str] = []
        monkeypatch.setattr(api, "_eval_js", calls.append)
        monkeypatch.setattr(api, "_run_in_thread", lambda fn: fn())
        mock = AsyncMock(return_value=settings_result)
        monkeypatch.setattr(api._twitch, "set_chat_settings", mock)
        return api, calls, mock

    @staticmethod
    def _payload(calls: list[str]) -> dict[str, Any]:
        import json

        prefix = "window.onChatModeChanged("
        last = [c for c in calls if c.startswith(prefix)][-1]
        return json.loads(last[len(prefix) : -1])

    def test_rejects_unknown_mode(self, temp_config_dir: Any, monkeypatch: Any) -> None:
        api, calls, mock = self._api(monkeypatch, {"emote_mode": True})
        api.set_chat_mode("__class__", True)
        mock.assert_not_awaited()
        payload = self._payload(calls)
        assert payload["ok"] is False
        assert payload["error"]

    def test_ok_is_bool_not_dict(self, temp_config_dir: Any, monkeypatch: Any) -> None:
        api, calls, _ = self._api(monkeypatch, {"emote_mode": True})
        api.set_chat_mode("emote_mode", True)
        assert self._payload(calls) == {"ok": True, "mode": "emote_mode", "value": True}

    def test_empty_result_is_not_ok(
        self, temp_config_dir: Any, monkeypatch: Any
    ) -> None:
        api, calls, _ = self._api(monkeypatch, {})
        api.set_chat_mode("subscriber_mode", True)
        assert self._payload(calls)["ok"] is False

    def test_slow_wait_is_clamped(self, temp_config_dir: Any, monkeypatch: Any) -> None:
        api, _, mock = self._api(monkeypatch, {"slow_mode": True})
        api.set_chat_mode("slow_mode", True, 1)
        assert mock.await_args.kwargs["slow_mode_wait_time"] == 3
        api.set_chat_mode("slow_mode", True, 9999)
        assert mock.await_args.kwargs["slow_mode_wait_time"] == 120
