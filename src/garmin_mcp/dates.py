"""Date ranges for the range tools (local calendar days, inclusive)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

DEFAULT_DAYS = 7
MAX_DAYS = 31


def parse_day(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be YYYY-MM-DD, got {value!r}") from e


def resolve_range(
    start: str | None,
    end: str | None,
    today: date,
    default_days: int = DEFAULT_DAYS,
    max_days: int = MAX_DAYS,
) -> tuple[date, date]:
    """Default: the last ``default_days`` days ending today."""
    end_d = parse_day(end, "end_date") if end else today
    start_d = parse_day(start, "start_date") if start else end_d - timedelta(days=default_days - 1)
    if start_d > end_d:
        raise ValueError("start_date must not be after end_date")
    span = (end_d - start_d).days + 1
    if span > max_days:
        raise ValueError(f"Range is {span} days; ask for at most {max_days} at a time.")
    return start_d, end_d


def each_day(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def chunks(start: date, end: date, size: int) -> Iterator[tuple[date, date]]:
    d = start
    while d <= end:
        last = min(end, d + timedelta(days=size - 1))
        yield d, last
        d = last + timedelta(days=1)
