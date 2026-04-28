from __future__ import annotations

import json
import threading
from typing import Any

from core.launcher import launch_stream
from core.storage import get_settings, load_config, update_config
from core.stream_resolver import resolve_hls_url

from ._base import BaseApiComponent

_MAX_LAUNCH_SECONDS = 20


class StreamsComponent(BaseApiComponent):
    """Video playback (native, external, multistream)."""

    # ── Watch ──────────────────────────────────────────────────

    def watch(self, channel: str, quality: str) -> None:
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return

        if self._api._watching_channel is not None or self._api._launch_channel is not None:
            return

        stream = self._api._data._find_live_stream(channel)
        platform = self._api._data._stream_platform(stream) if stream else "twitch"

        live_logins = {self._api._data._stream_login(s) for s in self._live_streams}
        if channel.lower() not in live_logins:
            safe_ch = json.dumps(channel)
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        def _save_quality(cfg: dict) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
        safe_ch = json.dumps(channel)
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )

        title = stream.get("title", "") if stream else ""

        if platform == "youtube":
            video_id = stream.get("video_id", "") if stream else ""
            if not video_id:
                r = json.dumps(
                    {
                        "success": False,
                        "message": "No live video found for this channel",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return

            self._api._launch_channel = channel
            self._api._launch_elapsed = 0
            self._start_launch_timer()

            def do_resolve_yt() -> None:
                settings = get_settings(self._config)
                hls_url, err = resolve_hls_url(
                    video_id,
                    quality,
                    settings.get("streamlink_path", "streamlink"),
                    platform="youtube",
                )
                self._cancel_launch_timer()
                self._api._launch_channel = None

                if not hls_url:
                    r = json.dumps(
                        {
                            "success": False,
                            "message": f"streamlink error: {err}"
                            if err
                            else "Could not resolve YouTube stream URL",
                            "channel": channel,
                        }
                    )
                    self._eval_js(f"window.onLaunchResult({r})")
                    return

                self._api._watching_channel = channel
                stream_data = json.dumps(
                    {
                        "url": hls_url,
                        "channel": channel,
                        "title": title,
                        "platform": "youtube",
                    }
                )
                self._eval_js(f"window.onStreamReady({stream_data})")
                r = json.dumps(
                    {
                        "success": True,
                        "message": f"Playing {channel}",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")

            self._run_in_thread(do_resolve_yt)
            return

        self._api._launch_channel = channel
        self._api._launch_elapsed = 0
        self._start_launch_timer()

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform=platform,
            )
            self._cancel_launch_timer()
            self._api._launch_channel = None

            if not hls_url:
                r = json.dumps(
                    {
                        "success": False,
                        "message": f"streamlink error: {err}"
                        if err
                        else "Could not resolve stream URL",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return

            self._api._watching_channel = channel
            stream_data = json.dumps(
                {
                    "url": hls_url,
                    "channel": channel,
                    "title": title,
                    "platform": platform,
                }
            )
            self._eval_js(f"window.onStreamReady({stream_data})")
            self._api._chat.start_chat(channel, platform)
            r = json.dumps(
                {
                    "success": True,
                    "message": f"Playing {channel}",
                    "channel": channel,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)

    def stop_player(self) -> None:
        self._api._chat.stop_chat()
        self._api._watching_channel = None
        self._eval_js("window.onPlayerStop()")

    def watch_direct(self, channel: str, platform: str, quality: str) -> None:
        if not channel:
            return
        if platform not in ("twitch", "kick"):
            self._eval_js(
                f"window.onLaunchResult({{success: false, "
                f"message: {json.dumps(f'{platform} stream playback is not supported')}, "
                f"channel: {json.dumps(channel)}}})"
            )
            return

        if self._api._watching_channel is not None or self._api._launch_channel is not None:
            return

        def _save_quality(cfg: dict[str, Any]) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
        safe_ch = json.dumps(channel)
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )
        self._api._launch_channel = channel
        self._api._launch_elapsed = 0
        self._start_launch_timer()

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform=platform,
            )
            self._cancel_launch_timer()
            self._api._launch_channel = None
            if not hls_url:
                r = json.dumps(
                    {
                        "success": False,
                        "message": err or "Could not resolve stream URL",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return
            self._api._watching_channel = channel
            stream_data = json.dumps(
                {"url": hls_url, "channel": channel, "title": "", "platform": platform}
            )
            self._eval_js(f"window.onStreamReady({stream_data})")
            self._api._chat.start_chat(channel, platform)
            r = json.dumps(
                {"success": True, "message": f"Playing {channel}", "channel": channel}
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)

    def watch_external(self, channel: str, quality: str) -> None:
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return

        stream = self._api._data._find_live_stream(channel)
        platform = self._api._data._stream_platform(stream) if stream else "twitch"

        live_logins = {self._api._data._stream_login(s) for s in self._live_streams}
        if channel.lower() not in live_logins:
            safe_ch = json.dumps(channel)
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        def do_launch() -> None:
            settings = get_settings(self._config)
            stream_channel = (
                stream.get("video_id", channel)
                if platform == "youtube" and stream
                else channel
            )
            result = launch_stream(
                stream_channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                settings.get(
                    "iina_path", "/Applications/IINA.app/Contents/MacOS/iina-cli"
                ),
                platform=platform,
            )
            r = json.dumps(
                {
                    "success": result.success,
                    "message": result.message,
                    "channel": channel,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_launch)

    def watch_media(
        self,
        url: str,
        quality: str,
        platform: str = "twitch",
        channel: str = "",
        title: str = "",
        with_chat: bool = False,
    ) -> None:
        if not url:
            return

        def _save_quality(cfg: dict[str, Any]) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
        display_name = channel or title or "media"
        safe_name = json.dumps(display_name)
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_name} + '...', type: 'warn'}})"
        )
        self._api._launch_channel = display_name
        self._api._launch_elapsed = 0
        self._start_launch_timer()

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = resolve_hls_url(
                url,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform=platform,
            )
            self._cancel_launch_timer()
            self._api._launch_channel = None
            if not hls_url:
                result = json.dumps(
                    {
                        "success": False,
                        "message": f"streamlink error: {err}"
                        if err
                        else "Could not resolve media URL",
                        "channel": display_name,
                    }
                )
                self._eval_js(f"window.onLaunchResult({result})")
                return

            self._api._chat.stop_chat()
            self._api._watching_channel = channel or display_name
            stream_data = json.dumps(
                {
                    "url": hls_url,
                    "channel": channel or display_name,
                    "title": title,
                    "platform": platform,
                    "has_chat": with_chat,
                }
            )
            self._eval_js(f"window.onStreamReady({stream_data})")
            if with_chat and channel:
                self._api._chat.start_chat(channel, platform)
            result = json.dumps(
                {
                    "success": True,
                    "message": f"Playing {display_name}",
                    "channel": channel or display_name,
                }
            )
            self._eval_js(f"window.onLaunchResult({result})")

        self._run_in_thread(do_resolve)

    # ── Multistream ─────────────────────────────────────────────

    def add_multi_slot(
        self, slot_idx: int, channel: str, platform: str, quality: str
    ) -> None:
        if not 0 <= slot_idx <= 3:
            return
        channel_lower = channel.lower() if platform != "youtube" else channel
        title = ""
        youtube_video_id: str | None = None
        for s in self._live_streams:
            if (
                self._api._data._stream_platform(s) == platform
                and self._api._data._stream_login(s) == channel_lower
            ):
                title = s.get("title", "")
                if platform == "youtube":
                    youtube_video_id = s.get("video_id") or None
                break

        if platform == "youtube" and not youtube_video_id:
            error_payload = json.dumps(
                {
                    "slot_idx": slot_idx,
                    "channel": channel,
                    "platform": platform,
                    "title": title,
                    "error": "YouTube channel is not currently live or stream info unavailable",
                }
            )
            self._eval_js(f"window.onMultiSlotReady({error_payload})")
            return

        def do_resolve() -> None:
            cfg = load_config()
            settings = get_settings(cfg)
            resolve_channel = youtube_video_id if youtube_video_id else channel
            hls_url, err = resolve_hls_url(
                resolve_channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform=platform,
            )
            payload: dict[str, Any] = {
                "slot_idx": slot_idx,
                "channel": channel,
                "platform": platform,
                "title": title,
            }
            if hls_url:
                payload["url"] = hls_url
            else:
                payload["error"] = err or "Could not resolve stream URL"
            self._eval_js(f"window.onMultiSlotReady({json.dumps(payload)})")

        self._run_in_thread(do_resolve)

    def stop_multi(self) -> None:
        self._api._chat.stop_chat()

    # ── Launch timer ────────────────────────────────────────────

    def _start_launch_timer(self) -> None:
        self._cancel_launch_timer()

        def tick() -> None:
            ch = self._api._launch_channel
            if not self._shutdown.is_set() and ch:
                self._api._launch_elapsed += 3
                elapsed = self._api._launch_elapsed
                if elapsed >= _MAX_LAUNCH_SECONDS:
                    safe_ch = json.dumps(ch)
                    self._eval_js(
                        f"window.onLaunchResult({{success: false, "
                        f"message: 'Timed out after {elapsed}s waiting for streamlink', "
                        f"channel: {safe_ch}}})"
                    )
                    self._api._launch_channel = None
                    return
                safe_ch = json.dumps(ch)
                self._eval_js(
                    f"window.onLaunchProgress({{channel: {safe_ch}, elapsed: {elapsed}}})"
                )
                self._start_launch_timer()

        self._api._launch_timer = threading.Timer(3.0, tick)
        self._api._launch_timer.daemon = True
        self._api._launch_timer.start()

    def _cancel_launch_timer(self) -> None:
        if self._api._launch_timer:
            self._api._launch_timer.cancel()
            self._api._launch_timer = None
