"""
Factory for picking the active TimelineProvider implementation.

Controlled by a single env var: TIMELINE_SOURCE=local (default) | remote.
This is the ONLY place that decides which implementation is active - every
caller elsewhere in Performance just calls get_timeline_provider() and uses
the interface, never importing LocalMockTimelineProvider or
RemoteTimelineProvider directly.
"""

import os

from timeline_source.base import TimelineProvider

_provider_instance: TimelineProvider = None


def get_timeline_provider() -> TimelineProvider:
    global _provider_instance
    if _provider_instance is None:
        source = os.getenv("TIMELINE_SOURCE", "local").strip().lower()
        if source == "remote":
            from timeline_source.remote_provider import RemoteTimelineProvider

            _provider_instance = RemoteTimelineProvider()
        else:
            from timeline_source.local_provider import LocalMockTimelineProvider

            _provider_instance = LocalMockTimelineProvider()
    return _provider_instance
