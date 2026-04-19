from __future__ import annotations

from ui.api import _aggregate_categories


def test_merges_categories_with_same_name() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "33214", "name": "Fortnite",
             "box_art_url": "https://img.jpg", "viewers": 0}
        ],
        "kick": [
            {"platform": "kick", "category_id": "42", "name": "Fortnite",
             "box_art_url": "", "viewers": 0}
        ],
    }
    result = _aggregate_categories(by_platform)
    assert len(result) == 1
    assert result[0]["name"] == "Fortnite"
    assert set(result[0]["platforms"]) == {"twitch", "kick"}
    assert result[0]["platform_ids"]["twitch"] == "33214"
    assert result[0]["platform_ids"]["kick"] == "42"


def test_keeps_distinct_names_separate() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "1", "name": "Fortnite",
             "box_art_url": "", "viewers": 0},
            {"platform": "twitch", "category_id": "2", "name": "Minecraft",
             "box_art_url": "", "viewers": 0},
        ],
    }
    result = _aggregate_categories(by_platform)
    assert {r["name"] for r in result} == {"Fortnite", "Minecraft"}


def test_merges_case_insensitively() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "1", "name": "Just Chatting",
             "box_art_url": "", "viewers": 0}
        ],
        "kick": [
            {"platform": "kick", "category_id": "9", "name": "just chatting",
             "box_art_url": "", "viewers": 0}
        ],
    }
    result = _aggregate_categories(by_platform)
    assert len(result) == 1


def test_prefers_first_nonempty_box_art_url() -> None:
    by_platform = {
        "twitch": [
            {"platform": "twitch", "category_id": "1", "name": "Fortnite",
             "box_art_url": "https://twitch.jpg", "viewers": 0}
        ],
        "youtube": [
            {"platform": "youtube", "category_id": "20", "name": "Fortnite",
             "box_art_url": "", "viewers": 0}
        ],
    }
    result = _aggregate_categories(by_platform)
    assert result[0]["box_art_url"] == "https://twitch.jpg"


def test_sorts_by_viewers_descending() -> None:
    by_platform = {
        "kick": [
            {"platform": "kick", "category_id": "1", "name": "Fortnite",
             "box_art_url": "", "viewers": 100},
            {"platform": "kick", "category_id": "2", "name": "Minecraft",
             "box_art_url": "", "viewers": 500},
        ]
    }
    result = _aggregate_categories(by_platform)
    assert result[0]["name"] == "Minecraft"
    assert result[1]["name"] == "Fortnite"
