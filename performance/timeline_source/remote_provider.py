"""
RemoteTimelineProvider - FUTURE implementation of TimelineProvider that
calls the real Timeline component's API once it exists.

Not usable yet - the real Timeline API doesn't exist, so there is nothing
concrete to call. This class is scaffolded now so the shape of the future
work is visible, and so TIMELINE_SOURCE=remote fails loudly and clearly
(NotImplementedError with an explanation) rather than silently misbehaving
if someone flips the env var before this is actually built.

When Timeline's API is ready:
    1. Fill in TIMELINE_SERVICE_BASE_URL (env var) and the HTTP calls below.
    2. Map Timeline's response shape to the exact dict shapes documented in
       base.py - that mapping is the ONLY thing that needs to change.
    3. No other file in Performance needs to change, because main.py and
       dashboard_feed.py only ever call the TimelineProvider interface,
       never this class directly.

Deliberately does NOT implement create_project/create_phase (see
local_provider.py's docstring) - in the final architecture, Timeline owns
creating projects/phases, not Performance.
"""

import os

from timeline_source.base import TimelineProvider


class RemoteTimelineProvider(TimelineProvider):
    def __init__(self):
        self.base_url = os.getenv("TIMELINE_SERVICE_BASE_URL")

    def _not_ready(self):
        raise NotImplementedError(
            "RemoteTimelineProvider is not implemented yet - the real Timeline "
            "component/API does not exist. Set TIMELINE_SOURCE=local until it "
            "does, then implement this class's methods against Timeline's API."
        )

    def list_projects(self) -> list[dict]:
        self._not_ready()

    def get_project(self, project_id: int) -> dict | None:
        self._not_ready()

    def list_phases(self, project_id: int) -> list[dict]:
        self._not_ready()

    def get_phase(self, phase_id: int) -> dict | None:
        self._not_ready()
