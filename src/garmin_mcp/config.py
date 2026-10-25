"""Where the server keeps its tokens.

Everything lives in one folder outside the repo, ``~/.garmin-mcp`` by default
(override with ``GARMIN_MCP_HOME``). It only ever holds the token file written
by the Garmin client and a lock file; your password is never stored.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path

    @property
    def token_file(self) -> Path:
        # garminconnect writes ``garmin_tokens.json`` inside the tokenstore folder.
        return self.home / "garmin_tokens.json"

    @property
    def lock_file(self) -> Path:
        return self.home / ".lock"


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    home = env.get("GARMIN_MCP_HOME") or str(Path.home() / ".garmin-mcp")
    return Config(home=Path(home).expanduser())
