"""One logged-in Garmin client per process, safe to share with other processes.

Garmin hands out a refresh token with the login and rotates it when the access
token is refreshed. The client library refreshes and saves the new tokens by
itself, but only knows about its own process. The MCP server and the export
CLI can run at the same time, so every call here:

* holds an exclusive lock file for the duration of the call, so only one
  process can refresh at a time, and
* reloads the token file first if another process changed it, so nobody
  refreshes with a refresh token that was already used.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib
import os
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from .config import Config
from .errors import NotConnectedError, RateLimitedError

T = TypeVar("T")

Factory = Callable[[], Any]


def default_factory() -> Factory:
    """The real Garmin client, or a stand-in named by GARMIN_MCP_FAKE (tests only)."""
    fake = os.environ.get("GARMIN_MCP_FAKE")
    if fake:
        module, _, attr = fake.partition(":")
        return getattr(importlib.import_module(module), attr)

    from garminconnect import Garmin

    return Garmin


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _errors() -> tuple[type[BaseException], type[BaseException]]:
    try:
        from garminconnect import (
            GarminConnectAuthenticationError,
            GarminConnectTooManyRequestsError,
        )
    except ImportError:  # pragma: no cover - library always installed in practice
        return (type("_NoAuth", (Exception,), {}), type("_NoRate", (Exception,), {}))
    return GarminConnectAuthenticationError, GarminConnectTooManyRequestsError


class GarminSession:
    def __init__(self, cfg: Config, factory: Factory | None = None) -> None:
        self.cfg = cfg
        self._factory = factory or default_factory()
        self._api: Any = None
        self._seen_mtime: float | None = None
        self._lock = threading.Lock()

    def call(self, fn: Callable[[Any], T]) -> T:
        """Run ``fn(api)`` with a logged-in client under the cross-process lock."""
        auth_error, rate_error = _errors()
        with self._lock, file_lock(self.cfg.lock_file):
            try:
                api = self._ensure_client()
                return fn(api)
            except auth_error as e:
                self._api = None
                raise NotConnectedError("Garmin rejected the saved login.") from e
            except rate_error as e:
                raise RateLimitedError() from e
            finally:
                # Our own refresh may have rewritten the file; that is not a
                # change by someone else.
                self._seen_mtime = _mtime(self.cfg.token_file)

    def _ensure_client(self) -> Any:
        mtime = _mtime(self.cfg.token_file)
        if mtime is None:
            self._api = None
            raise NotConnectedError()
        if self._api is None:
            api = self._factory()
            # Tokens only: no password is ever given to the server.
            api.login(tokenstore=str(self.cfg.home))
            self._api = api
        elif mtime != self._seen_mtime:
            self._api.client.load(str(self.cfg.home))
        self._seen_mtime = mtime
        return self._api
