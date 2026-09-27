from __future__ import annotations

import json
import logging
import threading
from typing import Any

from core.codecs import twitch_codec_args
from core.constants import CODEC_MODE_AUTO, DEFAULT_IINA_PATH, DEFAULT_MPV_PATH
from core.launcher import launch_stream, launch_stream_mpv
from core.storage import get_settings, load_config, update_config
from core.stream_resolver import (
    ADAPTIVE_PLATFORMS,
    invalidate_resolve_cache,
    resolve_hls_url,
)

from ._base import BaseApiComponent

logger = logging.getLogger(__name__)

# streamlink itself gives up after 15s, so a longer ceiling here only delays the
# error the user sees when the resolver thread hangs somewhere else.
_MAX_LAUNCH_SECONDS = 20


class StreamsComponent(BaseApiComponent):
    """Video playback (native, external, multistream)."""

    def _low_latency_args(self, platform: str, settings: dict) -> list[str]:
        """Return --twitch-low-latency if setting is enabled for Twitch."""
        if platform == "twitch" and settings.get("low_latency_mode", False):
            return ["--twitch-low-latency"]
        return []

    def _codec_args(self, platform: str, settings: dict) -> list[str]:
        """Return --twitch-supported-codecs for Twitch, nothing elsewhere."""
        if platform != "twitch":
            return []
        return twitch_codec_args(
            settings.get("stream_codecs", CODEC_MODE_AUTO),
            self._api._av1_capable,
        )

    def _streamlink_args(
        self, platform: str, settings: dict, low_latency: bool = True
    ) -> list[str]:
        """Build the streamlink flags for one resolve.

        The codec set decides whether Twitch offers its Enhanced Broadcasting
        renditions (1440p60 and above) at all, so it belongs to every resolve —
        including the external-player and multistream paths.

        low_latency is opt-out for recording: a reduced live edge trades buffer
        for delay, which is the wrong trade when the goal is a complete file.
        """
        args = self._low_latency_args(platform, settings) if low_latency else []
        return args + self._codec_args(platform, settings)

    def _invalidate_resolve_for(self, channel: str, platform: str) -> None:
        """Drop cached resolutions for one channel only.

        Clearing the whole cache would also evict the other multistream slots,
        which are refreshed independently.
        """
        if channel.startswith("http://") or channel.startswith("https://"):
            invalidate_resolve_cache(channel)
            return
        client = self._get_platform(platform)
        if client is not None:
            invalidate_resolve_cache(client.build_stream_url(channel))

    def _resolve_for_player(
        self,
        target: str,
        quality: str,
        platform: str,
        settings: dict,
        use_cache: bool = True,
    ) -> tuple[str | None, str]:
        """Resolve an HLS URL for the in-app AVPlayer.

        AVPlayer performs its own adaptive bitrate switching, so for quality="best"
        it is handed the master playlist and picks the rendition itself instead of
        being locked to whatever bitrate streamlink chose at resolve time.
        """
        return resolve_hls_url(
            target,
            quality,
            settings.get("streamlink_path", "streamlink"),
            platform_client=self._get_platform(platform),
            extra_args=self._streamlink_args(platform, settings),
            adaptive=platform in ADAPTIVE_PLATFORMS,
            use_cache=use_cache,
        )

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

    def _cancel_pending_launch(self) -> None:
        """Abandon an in-flight launch so a newer one can take over.

        Bumping _launch_id makes the older resolver thread fail _is_launch_current
        and drop its result instead of racing the new stream onto the player.
        """
        if self._api._launch_channel is None:
            return
        logger.debug("Superseding pending launch for %s", self._api._launch_channel)
        self._cancel_launch_timer()
        self._api._launch_channel = None
        self._api._launch_id += 1

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
        self.watch_platform(channel, "", quality)

    def watch_platform(self, channel: str, platform: str, quality: str) -> None:
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return

        stream = self._api._data._find_live_stream(channel, platform or None)
        platform = (
            self._api._data._stream_platform(stream) if stream else platform or "twitch"
        )

        safe_ch = json.dumps(channel)
        _watching = self._api._watching_channel
        _already = _watching is not None and (
            _watching == channel  # exact-case for YouTube UC IDs
            if platform == "youtube"
            else _watching.lower() == channel.lower()
        )
        if _already:
            self._eval_js(
                f"window.onStatusUpdate({{text: 'Already watching ' + {safe_ch}, type: 'info'}})"
            )
            return

        if not any(
            self._api._data._stream_matches_channel(s, channel, platform or None)
            for s in self._live_streams
        ):
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        # Past every validation, so this click is definitely going to launch:
        # only now may it supersede a launch that is still in flight. Cancelling
        # earlier threw away a good launch when the new pick turned out to be
        # offline or already playing.
        self._cancel_pending_launch()

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
                logger.info(
                    "Resolving YouTube stream for %s (quality=%s)", channel, quality
                )
                settings = get_settings(self._config)
                hls_url, err = self._resolve_for_player(
                    video_id, quality, "youtube", settings
                )
                if not self._finish_launch(launch_id):
                    logger.debug("Launch aborted for %s (launch_id mismatch)", channel)
                    return

                if not hls_url:
                    msg = err or "Could not resolve YouTube stream URL"
                    logger.warning(
                        "Failed to resolve YouTube stream for %s: %s", channel, msg
                    )
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

                logger.info("YouTube stream resolved for %s", channel)
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
                self._api._chat.start_chat(
                    channel, "youtube", live_chat_id=live_chat_id
                )
                r = json.dumps(
                    {
                        "success": True,
                        "message": f"Playing {channel}",
                        "channel": channel,
                        "platform": "youtube",
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")

            self._run_in_thread(do_resolve_yt)
            return

        launch_id = self._begin_launch(channel)

        def do_resolve() -> None:
            logger.info(
                "Resolving stream for %s on %s (quality=%s)", channel, platform, quality
            )
            settings = get_settings(self._config)
            hls_url, err = self._resolve_for_player(
                channel, quality, platform, settings
            )
            if not self._finish_launch(launch_id):
                logger.debug("Launch aborted for %s (launch_id mismatch)", channel)
                return

            if not hls_url:
                msg = err or "Could not resolve stream URL"
                logger.warning("Failed to resolve stream for %s: %s", channel, msg)
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

            logger.info("Stream resolved for %s on %s", channel, platform)
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
                    "platform": platform,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)

    def stop_player(self) -> None:
        self._end_watch_session()
        self._api._chat.stop_chat()
        self._api._watching_channel = None
        self._eval_js("window.onPlayerStop()")

    def notify_player_hidden(self) -> None:
        """Clear Python-side player state when JS hides the player without going through stop_player.

        Called by hidePlayerView() in cases where the player is dismissed directly from JS
        (Escape key, opening multistream) rather than via api.stop_player().
        Does not emit onPlayerStop to avoid re-entering hidePlayerView.
        """
        self._end_watch_session()
        self._api._chat.stop_chat()
        self._api._watching_channel = None

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

        def _save_quality(cfg: dict[str, Any]) -> None:
            cfg.get("settings", {})["quality"] = quality

        self._config = update_config(_save_quality)
        safe_ch = json.dumps(channel)
        _watching = self._api._watching_channel
        _already = _watching is not None and (
            _watching == channel
            if platform == "youtube"
            else _watching.lower() == channel.lower()
        )
        if _already:
            self._eval_js(
                f"window.onStatusUpdate({{text: 'Already watching ' + {safe_ch}, type: 'info'}})"
            )
            return
        self._eval_js(
            f"window.onStatusUpdate({{text: 'Loading ' + {safe_ch} + '...', type: 'warn'}})"
        )
        # See watch_platform: supersede only once this launch is certain.
        self._cancel_pending_launch()
        launch_id = self._begin_launch(channel)

        def do_resolve() -> None:
            settings = get_settings(self._config)
            hls_url, err = self._resolve_for_player(
                channel, quality, platform, settings
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
                {
                    "url": hls_url,
                    "channel": channel,
                    "title": "",
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
                    "platform": platform,
                }
            )
            self._eval_js(f"window.onLaunchResult({r})")

        self._run_in_thread(do_resolve)

    def save_quality(self, quality: str) -> None:
        """Persist the quality a live switch landed on.

        Launching a stream stores the picked quality, but switching quality on a
        running stream went through refresh_stream_url, which does not. Without
        this the next launch reverts, and a recording is made at a quality nobody
        is watching.
        """
        if not quality:
            return

        def _save(cfg: dict[str, Any]) -> None:
            cfg.setdefault("settings", {})["quality"] = quality

        self._config = update_config(_save)

    # ── URL refresh (player recovery) ───────────────────────────

    def refresh_stream_url(
        self, channel: str, platform: str, quality: str, request_id: int = 0
    ) -> None:
        """Re-resolve a live stream URL for a player that lost its stream.

        Signed HLS URLs expire, so replaying the URL the player was started with
        cannot recover a session that has been running for hours, or one that was
        interrupted by sleep or a network change. The cache is bypassed for the
        same reason.

        request_id is echoed back untouched so the player can drop a reply that
        arrived after it had already given up on (or no longer needed) the request.
        """
        if not channel:
            return
        platform = platform or "twitch"
        if platform == "youtube":
            # YouTube playback is keyed by video_id, which the player does not carry.
            payload = json.dumps(
                {
                    "ok": False,
                    "request_id": request_id,
                    "channel": channel,
                    "platform": platform,
                    "error": "Reconnect is not supported for YouTube",
                }
            )
            self._eval_js(f"window.onStreamUrlRefreshed({payload})")
            return

        def do_refresh() -> None:
            # The cached entry is what went stale in the first place.
            self._invalidate_resolve_for(channel, platform)
            settings = get_settings(load_config())
            hls_url, err = self._resolve_for_player(
                channel, quality, platform, settings, use_cache=False
            )
            payload = {
                "ok": bool(hls_url),
                "request_id": request_id,
                "url": hls_url or "",
                "channel": channel,
                "platform": platform,
                "quality": quality,
                "error": "" if hls_url else (err or "Could not resolve stream URL"),
            }
            self._eval_js(f"window.onStreamUrlRefreshed({json.dumps(payload)})")

        self._run_in_thread(do_refresh)

    def refresh_multi_slot_url(
        self,
        slot_idx: int,
        channel: str,
        platform: str,
        quality: str,
        request_id: int = 0,
    ) -> None:
        """Re-resolve the URL for one multistream slot. See refresh_stream_url."""
        if not 0 <= slot_idx <= 3 or not channel:
            return
        platform = platform or "twitch"

        def do_refresh() -> None:
            self._invalidate_resolve_for(channel, platform)
            settings = get_settings(load_config())
            hls_url, err = self._resolve_for_player(
                channel, quality, platform, settings, use_cache=False
            )
            payload = {
                "slot_idx": slot_idx,
                "ok": bool(hls_url),
                "request_id": request_id,
                "url": hls_url or "",
                # Echoed so a slot that changed channel mid-flight can tell that
                # this URL belongs to whoever used to occupy it.
                "channel": channel,
                "platform": platform,
                "error": "" if hls_url else (err or "Could not resolve stream URL"),
            }
            self._eval_js(f"window.onMultiSlotUrlRefreshed({json.dumps(payload)})")

        self._run_in_thread(do_refresh)

    def watch_external(self, channel: str, quality: str) -> None:
        self.watch_external_platform(channel, "", quality)

    def watch_external_platform(
        self, channel: str, platform: str, quality: str
    ) -> None:
        if not channel:
            self._eval_js(
                "window.onLaunchResult({success: false, message: 'Select a channel first', channel: ''})"
            )
            return

        stream = self._api._data._find_live_stream(channel, platform or None)
        platform = (
            self._api._data._stream_platform(stream) if stream else platform or "twitch"
        )

        if not any(
            self._api._data._stream_matches_channel(s, channel, platform or None)
            for s in self._live_streams
        ):
            safe_ch = json.dumps(channel)
            self._eval_js(
                f"window.onLaunchResult({{success: false, message: {safe_ch} + ' is offline', channel: {safe_ch}}})"
            )
            return

        if platform == "youtube":
            video_id = stream.get("video_id", "") if stream else ""
            if not video_id:
                safe_ch = json.dumps(channel)
                r = json.dumps(
                    {
                        "success": False,
                        "message": "No live video found for this YouTube channel",
                        "channel": channel,
                    }
                )
                self._eval_js(f"window.onLaunchResult({r})")
                return

        def do_launch() -> None:
            settings = get_settings(self._config)
            stream_channel = (
                stream.get("video_id", channel)
                if platform == "youtube" and stream
                else channel
            )
            platform_client = self._get_platform(platform)
            extra = self._streamlink_args(platform, settings)
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
            # VODs and clips stay on a single rendition: the master-playlist path is
            # tuned for live edge behaviour, while seeking and duration reporting
            # here depend on the concrete media playlist.
            hls_url, err = resolve_hls_url(
                url,
                quality,
                settings.get("streamlink_path", "streamlink"),
                platform_client=platform_client,
                extra_args=self._streamlink_args(platform, settings),
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
        if platform not in ("twitch", "kick", "youtube"):
            error_payload = json.dumps(
                {
                    "slot_idx": slot_idx,
                    "channel": channel,
                    "platform": platform,
                    "title": "",
                    "error": f"{platform} is not supported in multistream",
                }
            )
            self._eval_js(f"window.onMultiSlotReady({error_payload})")
            return
        title = ""
        youtube_video_id: str | None = None
        for s in self._live_streams:
            if self._api._data._stream_platform(
                s
            ) == platform and self._api._data._stream_matches_channel(s, channel):
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
                    "error": "YouTube multistream works only for live channels already loaded in TwitchX",
                }
            )
            self._eval_js(f"window.onMultiSlotReady({error_payload})")
            return

        def do_resolve() -> None:
            cfg = load_config()
            settings = get_settings(cfg)
            resolve_channel = youtube_video_id if youtube_video_id else channel
            hls_url, err = self._resolve_for_player(
                resolve_channel, quality, platform, settings
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
        stream_url = (
            platform_client.build_stream_url(channel) if platform_client else channel
        )

        # The recorder pulls its own copy of the stream, so recording at source
        # while watching doubles the downstream bandwidth. Recording at the
        # quality being watched keeps that second pull proportional.
        err = self._api._recorder.start(
            stream_url,
            channel,
            output_dir,
            streamlink_path,
            quality=settings.get("quality", "best"),
            extra_args=self._streamlink_args(platform, settings, low_latency=False),
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

    # ── Multistream layout presets ──────────────────────────────

    def get_multistream_presets(self) -> dict[str, Any]:
        """Return saved preset IDs and the active preset index."""
        config = load_config()
        settings = get_settings(config)
        presets = settings.get(
            "multistream_presets", ["grid", "focus-left", "rows", "columns"]
        )
        active = settings.get("multistream_active_preset", 0)
        if not isinstance(presets, list) or len(presets) < 1:
            presets = ["grid", "focus-left", "rows", "columns"]
        if not isinstance(active, int) or active < 0 or active >= len(presets):
            active = 0
        return {"presets": presets, "active": active}

    def set_multistream_preset(self, index: int) -> None:
        """Persist the active multistream preset index."""
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return
        config = load_config()
        settings = get_settings(config)
        presets = settings.get(
            "multistream_presets", ["grid", "focus-left", "rows", "columns"]
        )
        if not isinstance(presets, list) or len(presets) < 1:
            presets = ["grid", "focus-left", "rows", "columns"]
        if idx < 0 or idx >= len(presets):
            return
        update_config(
            lambda cfg: cfg.setdefault("settings", {}).__setitem__(
                "multistream_active_preset", idx
            )
        )
        self._eval_js(
            f"window.onMultistreamPresetChanged({json.dumps({'active': idx, 'preset': presets[idx]})})"
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
