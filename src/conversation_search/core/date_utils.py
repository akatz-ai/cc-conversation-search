#!/usr/bin/env python3
"""Date parsing utilities for conversation search"""

from datetime import datetime, timedelta, time
from typing import Tuple, List


def parse_date(date_str: str) -> datetime:
    """
    Parse flexible date inputs into datetime objects.

    Supports:
    - ISO format: "2025-11-13"
    - Relative: "yesterday", "today"

    Args:
        date_str: Date string to parse

    Returns:
        datetime object at start of day (midnight)

    Raises:
        ValueError: If date format is invalid
    """
    lower = date_str.lower().strip()

    # Relative dates
    if lower == 'yesterday':
        return datetime.combine(
            (datetime.now().date() - timedelta(days=1)),
            time.min
        )
    elif lower == 'today':
        return datetime.combine(datetime.now().date(), time.min)

    # ISO format (YYYY-MM-DD)
    try:
        parsed = datetime.fromisoformat(date_str)
        # Ensure we're at midnight
        return datetime.combine(parsed.date(), time.min)
    except ValueError:
        raise ValueError(
            f"Invalid date format: '{date_str}'. "
            f"Use YYYY-MM-DD, 'today', or 'yesterday'"
        )


def build_date_filter(
    since: str | None = None,
    until: str | None = None,
    date: str | None = None
) -> Tuple[str, List[str]]:
    """
    Build SQL WHERE clause and parameters for date filtering.

    Args:
        since: Start date (inclusive)
        until: End date (inclusive)
        date: Specific date (both start and end)

    Returns:
        (sql_clause, params) tuple

    Examples:
        >>> build_date_filter(date="2025-11-13")
        ("timestamp >= ? AND timestamp < ?", ["2025-11-13T00:00:00", "2025-11-14T00:00:00"])

        >>> build_date_filter(since="yesterday", until="today")
        ("timestamp >= ? AND timestamp < ?", ["2025-11-12T00:00:00", "2025-11-14T00:00:00"])
    """
    if date:
        # Single day: midnight to midnight next day
        start = parse_date(date)
        end = start + timedelta(days=1)
        return (
            "timestamp >= ? AND timestamp < ?",
            [start.isoformat(), end.isoformat()]
        )

    clauses = []
    params = []

    if since:
        start = parse_date(since)
        clauses.append("timestamp >= ?")
        params.append(start.isoformat())

    if until:
        # Until is inclusive, so add one day
        end = parse_date(until) + timedelta(days=1)
        clauses.append("timestamp < ?")
        params.append(end.isoformat())

    if not clauses:
        return ("", [])

    return (" AND ".join(clauses), params)
