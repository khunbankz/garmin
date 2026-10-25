"""Errors the tools turn into short, actionable messages."""

from __future__ import annotations

AUTH_HINT = "On the Mac, run `uv run garmin-mcp-auth` in the garmin-mcp folder, then try again."


class GarminMcpError(Exception):
    """Base class for errors shown to the user as-is."""


class NotConnectedError(GarminMcpError):
    def __init__(self, detail: str = "Garmin is not connected yet.") -> None:
        super().__init__(f"{detail} {AUTH_HINT}")


class RateLimitedError(GarminMcpError):
    def __init__(self) -> None:
        super().__init__(
            "Garmin is rate limiting requests right now. Wait a few minutes and try again."
        )
