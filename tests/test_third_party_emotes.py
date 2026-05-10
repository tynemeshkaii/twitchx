from __future__ import annotations

from core.third_party_emotes import (
    build_emote_map,
    parse_7tv_global,
    parse_bttv_channel,
    parse_bttv_global,
    parse_ffz_channel,
    parse_ffz_global,
)


class TestParseBttvGlobal:
    def test_parses_id_and_code(self) -> None:
        raw = [
            {"id": "abc123", "code": "Kappa", "imageType": "png"},
            {"id": "def456", "code": "PogChamp", "imageType": "png"},
        ]
        result = parse_bttv_global(raw)
        assert result == {
            "Kappa": "https://cdn.betterttv.net/emote/abc123/1x",
            "PogChamp": "https://cdn.betterttv.net/emote/def456/1x",
        }

    def test_skips_invalid_entries(self) -> None:
        raw = [{"id": ""}, {"code": "test"}]
        result = parse_bttv_global(raw)
        assert result == {}


class TestParseBttvChannel:
    def test_parses_channel_emotes(self) -> None:
        raw = {
            "channelEmotes": [{"id": "c1", "code": "myEmote", "imageType": "png"}],
            "sharedEmotes": [{"id": "s1", "code": "sharedOne", "imageType": "png"}],
        }
        result = parse_bttv_channel(raw)
        assert "myEmote" in result
        assert "sharedOne" in result
        assert result["myEmote"] == "https://cdn.betterttv.net/emote/c1/1x"

    def test_empty_payload(self) -> None:
        assert parse_bttv_channel({}) == {}


class TestParseFfzGlobal:
    def test_parses_sets(self) -> None:
        raw = {
            "sets": {
                "3": {
                    "emoticons": [
                        {
                            "id": 1,
                            "name": "LuL",
                            "urls": {"1": "//cdn.frankerfacez.com/emote/1/1"},
                        }
                    ]
                }
            }
        }
        result = parse_ffz_global(raw)
        assert "LuL" in result
        assert result["LuL"].startswith("https://cdn.frankerfacez.com/emote/1/1")

    def test_empty_sets(self) -> None:
        assert parse_ffz_global({}) == {}


class TestParseFfzChannel:
    def test_parses_room_sets(self) -> None:
        raw = {
            "room": {"set": 99},
            "sets": {
                "99": {
                    "emoticons": [
                        {
                            "id": 5,
                            "name": "OMEGALUL",
                            "urls": {"1": "//cdn.frankerfacez.com/emote/5/1"},
                        }
                    ]
                }
            },
        }
        result = parse_ffz_channel(raw)
        assert "OMEGALUL" in result

    def test_empty(self) -> None:
        assert parse_ffz_channel({}) == {}


class TestParse7tvGlobal:
    def test_parses_emotes(self) -> None:
        raw = {
            "emotes": [
                {
                    "id": "abc",
                    "name": "pepeLaugh",
                    "data": {
                        "host": {
                            "url": "//cdn.7tv.app/emote/abc",
                            "files": [
                                {"name": "1x.avif", "format": "AVIF"},
                                {"name": "1x.webp", "format": "WEBP"},
                            ],
                        }
                    },
                }
            ]
        }
        result = parse_7tv_global(raw)
        assert "pepeLaugh" in result

    def test_empty(self) -> None:
        assert parse_7tv_global({}) == {}


class TestBuildEmoteMap:
    def test_merges_maps_later_wins(self) -> None:
        a = {"Kappa": "https://a.com/kappa"}
        b = {"Kappa": "https://b.com/kappa", "LULW": "https://b.com/lulw"}
        result = build_emote_map(a, b)
        assert result["LULW"] == "https://b.com/lulw"
        assert result["Kappa"] == "https://b.com/kappa"