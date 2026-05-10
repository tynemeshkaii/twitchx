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
                fake_patch.last_url = url
                fake_patch.last_headers = headers
                fake_patch.last_params = params
                fake_patch.last_body = json
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
            assert patch_fn.last_url == "https://api.twitch.tv/helix/chat/settings"
            assert patch_fn.last_params == {
                "broadcaster_id": "111",
                "moderator_id": "222",
            }
            body = patch_fn.last_body
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
            body = patch_fn.last_body
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
            headers = patch_fn.last_headers
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