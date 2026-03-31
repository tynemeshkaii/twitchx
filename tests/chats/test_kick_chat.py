"""Tests for Kick Pusher chat client."""

from __future__ import annotations

from core.chat import Emote
from core.chats.kick_chat import parse_kick_emotes


class TestParseKickEmotes:
    def test_single_emote(self) -> None:
        text = "hello [emote:12345:KickHype] world"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "hello KickHype world"
        assert emotes == [
            Emote(
                code="KickHype",
                url="https://files.kick.com/emotes/12345/fullsize",
                start=6,
                end=13,
            )
        ]

    def test_multiple_emotes(self) -> None:
        text = "[emote:111:A] and [emote:222:B]"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "A and B"
        assert len(emotes) == 2
        assert emotes[0] == Emote(code="A", url="https://files.kick.com/emotes/111/fullsize", start=0, end=0)
        assert emotes[1] == Emote(code="B", url="https://files.kick.com/emotes/222/fullsize", start=6, end=6)

    def test_no_emotes(self) -> None:
        text = "hello world"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "hello world"
        assert emotes == []

    def test_empty_text(self) -> None:
        clean, emotes = parse_kick_emotes("")
        assert clean == ""
        assert emotes == []

    def test_adjacent_emotes(self) -> None:
        text = "[emote:1:A][emote:2:B]"
        clean, emotes = parse_kick_emotes(text)
        assert clean == "AB"
        assert emotes[0].start == 0
        assert emotes[0].end == 0
        assert emotes[1].start == 1
        assert emotes[1].end == 1
