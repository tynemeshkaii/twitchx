"""Fetch and cache third-party Twitch emotes from BTTV, FFZ, and 7TV."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BTTV_GLOBAL_URL = "https://api.betterttv.net/3/cached/emotes/global"
BTTV_CHANNEL_URL = "https://api.betterttv.net/3/cached/users/twitch/{user_id}"
FFZ_GLOBAL_URL = "https://api.frankerfacez.com/v1/set/global"
FFZ_CHANNEL_URL = "https://api.frankerfacez.com/v1/room/{channel}"
SEVENTV_GLOBAL_URL = "https://7tv.io/v3/emote-sets/global"
SEVENTV_CHANNEL_URL = "https://7tv.io/v3/users/twitch/{user_id}"

EMOTE_CACHE_TTL = 3600  # 1 hour


# ── Pure parsers ──────────────────────────────────────────────────────


def parse_bttv_global(data: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for e in data:
        eid = e.get("id", "")
        code = e.get("code", "")
        if eid and code:
            result[code] = f"https://cdn.betterttv.net/emote/{eid}/1x"
    return result


def parse_bttv_channel(data: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in ("channelEmotes", "sharedEmotes"):
        for e in data.get(key, []):
            eid = e.get("id", "")
            code = e.get("code", "")
            if eid and code:
                result[code] = f"https://cdn.betterttv.net/emote/{eid}/1x"
    return result


def parse_ffz_global(data: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for set_data in data.get("sets", {}).values():
        for e in set_data.get("emoticons", []):
            name = e.get("name", "")
            urls = e.get("urls", {})
            url = urls.get("1") or urls.get("2") or ""
            if name and url:
                if url.startswith("//"):
                    url = "https:" + url
                result[name] = url
    return result


def parse_ffz_channel(data: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    room = data.get("room", {})
    set_id = str(room.get("set", ""))
    sets = data.get("sets", {})
    target_set = sets.get(set_id, {})
    for e in target_set.get("emoticons", []):
        name = e.get("name", "")
        urls = e.get("urls", {})
        url = urls.get("1") or urls.get("2") or ""
        if name and url:
            if url.startswith("//"):
                url = "https:" + url
            result[name] = url
    return result


def parse_7tv_global(data: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for e in data.get("emotes", []):
        name = e.get("name", "")
        host_data = (e.get("data") or {}).get("host", {})
        host_url = host_data.get("url", "")
        files = host_data.get("files", [])
        # prefer WEBP 1x, fall back to first file
        file_name = ""
        for f in files:
            if f.get("format") in ("WEBP", "PNG") and "1x" in f.get("name", ""):
                file_name = f["name"]
                break
        if not file_name and files:
            file_name = files[0].get("name", "")
        if name and host_url and file_name:
            url = host_url + "/" + file_name
            if url.startswith("//"):
                url = "https:" + url
            result[name] = url
    return result


def parse_7tv_channel(data: dict[str, Any]) -> dict[str, str]:
    """Parse 7TV user emote set response."""
    emote_set = data.get("emote_set") or {}
    return parse_7tv_global(emote_set)


def build_emote_map(*maps: dict[str, str]) -> dict[str, str]:
    """Merge emote maps; later maps win on conflict."""
    result: dict[str, str] = {}
    for m in maps:
        result.update(m)
    return result


# ── HTTP fetch helpers ────────────────────────────────────────────────


def _get_json(url: str, timeout: float = 8.0) -> Any:
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug("Third-party emote fetch failed %s: %s", url, exc)
        return None


# ── Disk cache ────────────────────────────────────────────────────────


def _cache_path(cache_dir: str, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return Path(cache_dir) / f"{safe}.json"


def _load_cache(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data.get("_fetched_at", 0) > EMOTE_CACHE_TTL:
            return None
        return {k: v for k, v in data.items() if k != "_fetched_at"}
    except Exception:
        return None


def _save_cache(path: Path, emotes: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(emotes)
    payload["_fetched_at"] = time.time()  # type: ignore[assignment]
    try:
        path.write_text(json.dumps(payload))
    except OSError as exc:
        logger.debug("Failed to write emote cache %s: %s", path, exc)


# ── Public API ────────────────────────────────────────────────────────


def fetch_channel_emotes(
    channel: str,
    twitch_user_id: str,
    cache_dir: str,
) -> dict[str, str]:
    """Fetch BTTV + FFZ + 7TV emotes for a channel. Returns code→url map.

    Results are cached per-channel for EMOTE_CACHE_TTL seconds.
    """
    cache_key = f"channel_{channel}"
    cached = _load_cache(_cache_path(cache_dir, cache_key))
    if cached is not None:
        return cached

    maps: list[dict[str, str]] = []

    # BTTV global
    raw = _get_json(BTTV_GLOBAL_URL)
    if isinstance(raw, list):
        maps.append(parse_bttv_global(raw))

    # BTTV channel
    if twitch_user_id and twitch_user_id.strip():
        raw = _get_json(BTTV_CHANNEL_URL.format(user_id=twitch_user_id))
        if isinstance(raw, dict):
            maps.append(parse_bttv_channel(raw))

    # FFZ global
    raw = _get_json(FFZ_GLOBAL_URL)
    if isinstance(raw, dict):
        maps.append(parse_ffz_global(raw))

    # FFZ channel
    raw = _get_json(FFZ_CHANNEL_URL.format(channel=channel.lower()))
    if isinstance(raw, dict):
        maps.append(parse_ffz_channel(raw))

    # 7TV global
    raw = _get_json(SEVENTV_GLOBAL_URL)
    if isinstance(raw, dict):
        maps.append(parse_7tv_global(raw))

    # 7TV channel
    if twitch_user_id and twitch_user_id.strip():
        raw = _get_json(SEVENTV_CHANNEL_URL.format(user_id=twitch_user_id))
        if isinstance(raw, dict):
            maps.append(parse_7tv_channel(raw))

    result = build_emote_map(*maps)
    _save_cache(_cache_path(cache_dir, cache_key), result)
    return result