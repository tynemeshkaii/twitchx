from __future__ import annotations

import json
import threading
from typing import Any

from core.constants import DEFAULT_IINA_PATH, DEFAULT_MPV_PATH
from core.launcher import launch_stream, launch_stream_mpv
from core.storage import get_settings, load_config, update_config
from core.stream_resolver import resolve_hls_url

from ._base import BaseApiComponent

_MAX_LAUNCH_SECONDS = 20


class StreamsComponent(BaseApiComponent):
    """Video playback (native, external, multistream)."""

    def _low_latency_args(self, platform: str, settings: dict) -> list[str]:
        """Return --twitch-low-latency if setting is enabled for Twitch."""
        if platform == "twitch" and settings.get("low_latency_mode", False):
            return ["--twitch-low-latency"]
        return []

    # ── Watch session tracking ──────────────────────────────────

    def _end_watch_session(self) -> None:
        with self._api._active_watch_lock:
            if self._api._active_watch_session is not None:
                self._api._watch_stats.end_session(self._api._active_watch_session)
                self._api._active_watch_session = None

    def _start_watch_session(
        self,
        channel: str,
        platform: str,
        display_name: str = "",
        title: str = "",
        stream_type: str = "live",
    ) -> None:
        with self._api._active_watch_lock:
            if self._api._active_watch_session is not None:
                self._api._watch_stats.end_session(self._api._active_watch_session)
            session_id = self._api._watch_stats.start_session(
                channel=channel,
                platform=platform,
                display_name=display_name,
                title=title,
                stream_type=stream_type,
            )
            if session_id is not None:
                self._api._active_watch_session = session_id

    def _begin_launch(self, channel: str) -> int:
        self._api._launch_channel = channel
        self._api._launch_elapsed = 0
        self._api._launch_id += 1
        self._start_launch_timer()
        return self._api._launch_id

    def _is_launch_current(self, launch_id: int) -> bool:
        return self._api._launch_id == launch_id

    def _finish_launch(self, launch_id: int) -> bool:
        if not self._is_launch_current(launch_id):
            return False
        self._cancel_launch_timer()
        self._api._launch_channel = None
        self._api._launch_id += 1
        return True

    # ── Watch ──────────────────────────────────────────────────

    def watch(self, channel: str, quality: str) -> None:
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return

        if self._api._launch_channel is not None:
            return

        stream = self._api._data._find_live_stream(channel)
        platform = self._api._data._stream_platform(stream) if stream else "twitch"

        safe_ch = json.dumps(channel)
        if (
            self._api._watching_channel
            and self._api._watching_channel.lower() == channel.lower()
        ):
            self._eval_js(
                f"window.onStatusUpdate({{text: 'Already watching ' + {safe_ch}, type: 'info'}})"
            )
            return

        if not any(
            self._api._data._stream_matches_channel(s, channel)
            for s in self._live_streams
        ):
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        def _save_quality(cfg: dict) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
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

            launch_id = self._begin_launch(channel)

            def do_resolve_yt() -> None:
                settings = get_settings(self._config)
                hls_url, err = resolve_hls_url(
                    video_id,
                    quality,
                    settings.get("streamlink_path", "streamlink"),
                    platform_client=self._youtube,
                    extra_args=self._low_latency_args(platform, settings),
                )
                if not self._finish_launch(launch_id):
                    return

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

                self._api._chat.stop_chat()
                self._api._watching_channel = channel
                self._start_watch_session(
                    channel, "youtube", display_name=channel, title=title
                )
                live_chat_id = stream.get("live_chat_id", "") if stream else ""
                stream_data = json.dumps(
                    {
                        "url": hls_url,
                        "channel": channel,
                        "title": title,
                        "platform": "youtube",
                        "stream_type": "live",
                    }
                )
                self._eval_js(f"window.onStreamReady({stream_data})")
                self._api._chat.start_chat(channel, "youtube", live_chat_id=live_chat_id)
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

        launch_id = self._begin_launch(channel)

        def do_resolve() -> None:
            settings = get_settings(self._config)
            platform_client = self._get_platform(platform)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform_client=platform_client,
                extra_args=self._low_latency_args(platform, settings),
            )
            if not self._finish_launch(launch_id):
                return

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

            self._api._chat.stop_chat()
            self._api._watching_channel = channel
            self._start_watch_session(
                channel, platform, display_name=channel, title=title
            )
            stream_data = json.dumps(
                {
                    "url": hls_url,
                    "channel": channel,
                    "title": title,
                    "platform": platform,
                    "stream_type": "live",
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
        self._end_watch_session()
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

        if self._api._launch_channel is not None:
            return

        def _save_quality(cfg: dict[str, Any]) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
        safe_ch = json.dumps(channel)
        if (
            self._api._watching_channel
            and self._api._watching_channel.lower() == channel.lower()
        ):
            self._eval_js(
                f"window.onStatusUpdate({{text: 'Already watching ' + {safe_ch}, type: 'info'}})"
            )
            return
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )
        launch_id = self._begin_launch(channel)

        def do_resolve() -> None:
            settings = get_settings(self._config)
            platform_client = self._get_platform(platform)
            hls_url, err = resolve_hls_url(
                channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform_client=platform_client,
                extra_args=self._low_latency_args(platform, settings),
            )
            if not self._finish_launch(launch_id):
                return
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
            self._api._chat.stop_chat()
            self._api._watching_channel = channel
            self._start_watch_session(channel, platform, display_name=channel)
            stream_data = json.dumps(
                {"url": hls_url, "channel": channel, "title": "", "platform": platform, "stream_type": "live"}
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

        if not any(
            self._api._data._stream_matches_channel(s, channel)
            for s in self._live_streams
        ):
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
            platform_client = self._get_platform(platform)
            extra = self._low_latency_args(platform, settings)
            external = settings.get("external_player", "iina")

            if external == "mpv":
                mpv_path = settings.get("mpv_path", DEFAULT_MPV_PATH)
                result = launch_stream_mpv(
                    stream_channel,
                    quality,
                    settings.get("streamlink_path", "streamlink"),
                    mpv_path,
                    platform_client=platform_client,
                    extra_args=extra,
                )
            else:
                result = launch_stream(
                    stream_channel,
                    quality,
                    settings.get("streamlink_path", "streamlink"),
                    settings.get("iina_path", DEFAULT_IINA_PATH),
                    platform_client=platform_client,
                    extra_args=extra,
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
        launch_id = self._begin_launch(display_name)

        def do_resolve() -> None:
            settings = get_settings(self._config)
            platform_client = self._get_platform(platform)
            hls_url, err = resolve_hls_url(
                url,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform_client=platform_client,
                extra_args=self._low_latency_args(platform, settings),
            )
            if not self._finish_launch(launch_id):
                return
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
            self._start_watch_session(
                channel or display_name,
                platform,
                display_name=display_name,
                title=title,
            )
            stream_data = json.dumps(
                {
                    "url": hls_url,
                    "channel": channel or display_name,
                    "title": title,
                    "platform": platform,
                    "has_chat": with_chat,
                    "stream_type": "vod",
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
        title = ""
        youtube_video_id: str | None = None
        for s in self._live_streams:
            if (
                self._api._data._stream_platform(s) == platform
                and self._api._data._stream_matches_channel(s, channel)
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
            platform_client = self._get_platform(platform)
            hls_url, err = resolve_hls_url(
                resolve_channel,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform_client=platform_client,
                extra_args=self._low_latency_args(platform, settings),
            )
            payload: dict[str, Any] = {
                "slot_idx": slot_idx,
                "channel": channel,
                "platform": platform,
                "title": title,
            }
            if hls_url:
                payload["url"] = hls_url
                if self._api._active_watch_session is None:
                    self._start_watch_session(
                        channel,
                        platform,
                        display_name=channel,
                        title=title,
                        stream_type="multistream",
                    )
            else:
                payload["error"] = err or "Could not resolve stream URL"
            self._eval_js(f"window.onMultiSlotReady({json.dumps(payload)})")

        self._run_in_thread(do_resolve)

    def stop_multi(self) -> None:
        self._end_watch_session()
        self._api._chat.stop_chat()

    def start_recording(self) -> None:
        """Begin recording the currently watched channel."""
        channel = self._api._watching_channel
        if not channel:
            self._eval_js(
                "window.onRecordingState({active: false, filename: null, elapsed: 0, "
                "error: 'Not watching any channel'})"
            )
            return
        config = load_config()
        settings = get_settings(config)
        output_dir = settings.get("recording_path", "")
        streamlink_path = settings.get("streamlink_path", "streamlink")

        stream = self._api._data._find_live_stream(channel)
        platform = self._api._data._stream_platform(stream) if stream else "twitch"
        platform_client = self._get_platform(platform)
        stream_url = platform_client.build_stream_url(channel) if platform_client else channel

        err = self._api._recorder.start(
            stream_url, channel, output_dir, streamlink_path
        )
        if err:
            safe_err = json.dumps(err)
            self._eval_js(
                f"window.onRecordingState({{active: false, filename: null, elapsed: 0, error: {safe_err}}})"
            )
        else:
            state = json.dumps(self._api._recorder.state_dict())
            self._eval_js(f"window.onRecordingState({state})")

    def stop_recording(self) -> None:
        """Stop an active recording."""
        self._api._recorder.stop()
        self._eval_js(
            "window.onRecordingState({active: false, filename: null, elapsed: 0})"
        )

    # ── Launch timer ────────────────────────────────────────────

    def _start_launch_timer(self) -> None:
        self._cancel_launch_timer()

        def tick() -> None:
            ch = self._api._launch_channel
            launch_id = self._api._launch_id
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
                    self._api._launch_id += 1
                    return
                safe_ch = json.dumps(ch)
                self._eval_js(
                    f"window.onLaunchProgress({{channel: {safe_ch}, elapsed: {elapsed}}})"
                )
                if self._api._launch_id == launch_id:
                    self._start_launch_timer()

        self._api._launch_timer = threading.Timer(3.0, tick)
        self._api._launch_timer.daemon = True
        self._api._launch_timer.start()

    def _cancel_launch_timer(self) -> None:
        if self._api._launch_timer:
            self._api._launch_timer.cancel()
            self._api._launch_timer = None
