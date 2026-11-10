"""Stage 5 — video generation via veo-2.0-generate-001.

Rate-limited to 1 video per hour globally (enforced via Redis).
Polls the operation until complete or times out.
"""

from __future__ import annotations

import asyncio
import time

from utils.gemini_client import get_client
from utils.logger import get_logger
from utils.video_rate_limiter import check_and_set_rate_limit

_logger = get_logger("gemini_video_gen")

_MODEL = "veo-2.0-generate-001"
_POLL_INTERVAL_SECONDS = 10
_TIMEOUT_SECONDS = 300   # 5 minutes max wait


def _build_video_prompt(district: str, orientation: str, room_names: list[str]) -> str:
    rooms_str = ", ".join(room_names)
    return (
        f"Smooth cinematic 3D walkthrough of a modern Sri Lankan residential home in {district} "
        f"district. The house is {orientation}. The camera glides through: {rooms_str}. "
        f"Warm natural lighting, cream walls, wooden accents, tropical garden visible through windows. "
        f"Professional real estate videography style, steady Steadicam movement, 8 seconds."
    )


def _generate_video_sync(prompt: str) -> str | None:
    """Blocking Veo call with polling. Returns a public video URL or None on failure."""
    client = get_client()

    operation = client.models.generate_videos(
        model=_MODEL,
        prompt=prompt,
    )

    deadline = time.time() + _TIMEOUT_SECONDS
    while not operation.done:
        if time.time() > deadline:
            _logger.warning("Video generation timed out after %ds", _TIMEOUT_SECONDS)
            return None
        _logger.info("Video operation pending — polling in %ds", _POLL_INTERVAL_SECONDS)
        time.sleep(_POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)

    if operation.response and operation.response.generated_videos:
        video = operation.response.generated_videos[0]
        # video.video.uri is the GCS URI; return it as the video URL
        uri = getattr(video.video, "uri", None)
        _logger.info("Video generated: %s", uri)
        return uri

    _logger.warning("Video operation completed but no video in response")
    return None


async def generate_video(
    district: str,
    orientation: str,
    room_names: list[str],
) -> tuple[str | None, str | None]:
    """Generate a walkthrough video, respecting the rate limit.

    Returns:
        (video_url, skipped_reason)
        Exactly one of the two will be non-None.
    """
    is_allowed, minutes_remaining = check_and_set_rate_limit()

    if not is_allowed:
        reason = f"Rate limit active. Video generation available in {minutes_remaining} minute(s)."
        _logger.info("Video skipped: %s", reason)
        return None, reason

    prompt = _build_video_prompt(district, orientation, room_names)
    _logger.info("Starting video generation for %s (%s)", district, orientation)

    try:
        url = await asyncio.get_event_loop().run_in_executor(
            None, _generate_video_sync, prompt
        )
        if url:
            return url, None
        return None, "Video generation completed but no URL was returned."
    except Exception as exc:
        _logger.error("Video generation failed: %s", exc)
        return None, f"Video generation failed: {exc}"
