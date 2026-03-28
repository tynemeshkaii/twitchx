# tests/test_platform_models.py
from __future__ import annotations

from core.platform import (
    CategoryInfo,
    ChannelInfo,
    PlaybackInfo,
    StreamInfo,
    TokenData,
    UserInfo,
)


class TestStreamInfo:
    def test_create(self):
        s = StreamInfo(
            platform="twitch",
            channel_id="123",
            channel_login="xqc",
            display_name="xQc",
            title="VARIETY",
            category="Just Chatting",
            viewers=15000,
            started_at="2026-03-28T16:00:00Z",
            thumbnail_url="https://example.com/thumb.jpg",
            avatar_url="https://example.com/avatar.png",
        )
        assert s.platform == "twitch"
        assert s.channel_login == "xqc"
        assert s.viewers == 15000


class TestPlaybackInfo:
    def test_hls_type(self):
        p = PlaybackInfo(url="https://example.com/stream.m3u8", playback_type="hls", quality="best")
        assert p.playback_type == "hls"

    def test_youtube_embed_type(self):
        p = PlaybackInfo(url="dQw4w9WgXcQ", playback_type="youtube_embed", quality="best")
        assert p.playback_type == "youtube_embed"


class TestChannelInfo:
    def test_can_follow_via_api(self):
        c = ChannelInfo(
            platform="kick",
            channel_id="456",
            login="ninja",
            display_name="Ninja",
            bio="Pro gamer",
            avatar_url="",
            followers=10000,
            is_live=True,
            can_follow_via_api=False,
        )
        assert c.can_follow_via_api is False


class TestTokenData:
    def test_create(self):
        t = TokenData(access_token="abc", refresh_token="def", expires_at=9999999999.0, token_type="user")
        assert t.token_type == "user"


class TestUserInfo:
    def test_create(self):
        u = UserInfo(platform="youtube", user_id="UC123", login="pewdiepie", display_name="PewDiePie", avatar_url="")
        assert u.platform == "youtube"


class TestCategoryInfo:
    def test_create(self):
        c = CategoryInfo(platform="twitch", category_id="509658", name="Just Chatting", box_art_url="", viewers=500000)
        assert c.name == "Just Chatting"
