"""Log in to Garmin Connect once and save tokens for the server.

    uv run garmin-mcp-auth            # asks for email, password and MFA code if needed
    uv run garmin-mcp-auth --status   # is it connected?

You type your password here, in your own Terminal. It is sent only to Garmin's
login page and never written to disk; only the resulting tokens are saved to
~/.garmin-mcp/garmin_tokens.json (mode 600).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime

from .config import Config, load_config
from .errors import GarminMcpError
from .session import GarminSession, default_factory, file_lock


def status(cfg: Config) -> int:
    if not cfg.token_file.exists():
        print(f"Not connected. No tokens at {cfg.token_file}")
        return 1
    saved = datetime.fromtimestamp(cfg.token_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    try:
        name = GarminSession(cfg).call(lambda api: api.get_full_name() or api.display_name)
    except GarminMcpError as e:
        print(f"Tokens saved {saved}, but they do not work: {e}")
        return 1
    print(f"Connected as {name}. Tokens at {cfg.token_file} (last saved {saved}).")
    return 0


def login(cfg: Config) -> int:
    from garminconnect import (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )

    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (not shown): ")
    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        return 2

    def mfa() -> str:
        return input("Garmin sent you a code. Enter it: ").strip()

    api = default_factory()(email=email, password=password, prompt_mfa=mfa)
    del password
    try:
        with file_lock(cfg.lock_file):
            # No tokenstore here on purpose: always a fresh login, and the old
            # tokens stay in place until the new ones are written.
            api.login()
            api.client.dump(str(cfg.home))
    except GarminConnectTooManyRequestsError:
        print("Garmin is rate limiting logins. Wait 15-60 minutes, then try again.", file=sys.stderr)
        return 1
    except GarminConnectAuthenticationError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1
    except GarminConnectConnectionError as e:
        print(f"Could not reach Garmin: {e}", file=sys.stderr)
        return 1
    print(f"Connected as {api.full_name or api.display_name}. Tokens saved to {cfg.token_file}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="garmin-mcp-auth", description=__doc__.splitlines()[0])
    parser.add_argument("--status", action="store_true", help="check the saved login instead of logging in")
    args = parser.parse_args(argv)
    cfg = load_config()
    sys.exit(status(cfg) if args.status else login(cfg))


if __name__ == "__main__":
    main()
