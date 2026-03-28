# tests/test_chat_models.py
from __future__ import annotations

from core.chat import Badge, ChatClient, ChatMessage, ChatStatus, Emote


class TestChatMessage:
    def test_create_text_message(self):
        msg = ChatMessage(
            platform="twitch",
            author="viewer123",
            author_display="Viewer123",
            author_color="#FF0000",
            avatar_url=None,
            text="Hello stream!",
            timestamp="2026-03-28T16:00:00Z",
            badges=[Badge(name="subscriber", icon_url="https://example.com/sub.png")],
            emotes=[
                Emote(code="Kappa", url="https://example.com/kappa.png", start=0, end=4)
            ],
            is_system=False,
            message_type="text",
            raw={},
        )
        assert msg.platform == "twitch"
        assert msg.message_type == "text"
        assert len(msg.badges) == 1
        assert msg.badges[0].name == "subscriber"
        assert len(msg.emotes) == 1
        assert msg.emotes[0].code == "Kappa"


class TestChatStatus:
    def test_connected(self):
        s = ChatStatus(connected=True, platform="kick", channel_id="123", error=None)
        assert s.connected is True
        assert s.error is None

    def test_error(self):
        s = ChatStatus(
            connected=False, platform="youtube", channel_id="abc", error="Auth failed"
        )
        assert s.connected is False
        assert s.error == "Auth failed"


class TestChatClientIsAbstract:
    def test_cannot_instantiate(self):
        import pytest

        with pytest.raises(TypeError):
            ChatClient()  # type: ignore[abstract]
