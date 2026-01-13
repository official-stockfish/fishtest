#!/usr/bin/env python3
"""Analyze Nginx access logs grouped by Fishtest FastAPI routes.

This utility introspects the local Fishtest FastAPI app to discover routes and
then aggregates timing stats from Nginx access logs per route prefix.

By default, the CLI analyzes all lines from ``/var/log/nginx/access.log``.
Use ``--since``/``--until`` to filter entries in a time window (for example,
``"2026-02-14 12:00:00"``) or relative values (for example,
``"90 minutes ago"``, ``"1.5 h ago"``, ``"30 s ago"``), and ``--log-file``
to use a different source.

The default log path is commonly root-owned, so run with ``sudo`` when your
user cannot read it.
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

MAXCOUNT_THRESHOLD: Final[float] = 29.95
REQUEST_RE: Final[re.Pattern[str]] = re.compile(r'"[^" ]+ (?P<path>[^" ]+) [^"]+"')
DATE_RE: Final[re.Pattern[str]] = re.compile(r"\[(?P<date>[^\]]+)\]")
RELATIVE_TIME_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>hour|hours|h|minute|minutes|m|second|seconds|s)\s+ago\s*$",
    flags=re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class RouteStat:
    """Aggregated timing metrics for one route."""

    route: str
    calls: int
    total: float
    average: float
    minimum: float
    maximum: float
    maxcount: int


@dataclass(slots=True, frozen=True)
class LogWindow:
    """A bounded window of access log lines with derived summary fields."""

    lines: tuple[str, ...]
    start: datetime
    end: datetime


def _parse_args(
    argv: Sequence[str] | None = None,
    *,
    default_log_file: Path = Path("/var/log/nginx/access.log"),
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Tip: /var/log/nginx/access.log is often root-owned. "
            'Use sudo when required. Example: --since "2026-02-14 12:00:00" '
            '--until "2026-02-14 18:00:00" or --since "1.5 h ago".'
        ),
    )
    parser.add_argument(
        "-l",
        "--log-file",
        type=Path,
        default=default_log_file,
        help=f"Access log path (default: {default_log_file}).",
    )
    parser.add_argument(
        "-S",
        "--since",
        type=str,
        default="1 hours ago",
        help=(
            "Analyze only entries at/after this timestamp. "
            'Accepts journalctl-style "YYYY-MM-DD HH:MM:SS" '
            'and relative forms like "N minutes ago", "N.N h ago", "N s ago" '
            '(default: "1 hours ago").'
        ),
    )
    parser.add_argument(
        "-U",
        "--until",
        type=str,
        default=None,
        help=(
            "Analyze only entries at/before this timestamp. "
            'Accepts journalctl-style "YYYY-MM-DD HH:MM:SS" '
            'and relative forms like "N minutes ago", "N.N h ago", "N s ago".'
        ),
    )
    namespace = parser.parse_args(argv)
    namespace.log_file = namespace.log_file.expanduser()
    reference_now = datetime.now(UTC).replace(microsecond=0)

    if namespace.since is not None:
        try:
            namespace.since = _parse_bound_datetime(
                namespace.since,
                option_name="--since",
                reference_now=reference_now,
            )
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
    if namespace.until is not None:
        try:
            namespace.until = _parse_bound_datetime(
                namespace.until,
                option_name="--until",
                reference_now=reference_now,
            )
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
    if (
        namespace.since is not None
        and namespace.until is not None
        and namespace.since > namespace.until
    ):
        parser.error(
            "--since must be earlier than or equal to --until",
        )
    return namespace


def _server_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _extract_datetime(line: str) -> datetime:
    match = DATE_RE.search(line)
    if match is None:
        msg = "failed to extract date range from access log"
        raise ValueError(msg)
    return datetime.strptime(match.group("date"), "%d/%b/%Y:%H:%M:%S %z")


def _parse_bound_datetime(
    value: str,
    *,
    option_name: str,
    reference_now: datetime,
) -> datetime:
    relative_match = RELATIVE_TIME_RE.match(value)
    if relative_match is not None:
        amount = float(relative_match.group("amount"))
        unit = relative_match.group("unit").lower()
        if unit in {"hour", "hours", "h"}:
            delta_seconds = amount * 3600
        elif unit in {"minute", "minutes", "m"}:
            delta_seconds = amount * 60
        else:
            delta_seconds = amount
        return reference_now - timedelta(seconds=delta_seconds)

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = (
            f'invalid {option_name} value; expected "YYYY-MM-DD HH:MM:SS" '
            "(for example: 2026-02-14 12:00:00), relative forms like "
            '"N minutes ago", "N.N h ago", "N s ago", or ISO 8601'
        )
        raise argparse.ArgumentTypeError(msg) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _read_log_window(
    path: Path,
    *,
    since: datetime | None,
    until: datetime | None,
) -> LogWindow:
    with path.open(encoding="utf-8", errors="replace") as handle:
        lines = tuple(line.rstrip("\n") for line in handle)

    if since is not None or until is not None:
        filtered: list[str] = []
        for line in lines:
            line_datetime = _extract_datetime(line)
            if since is not None and line_datetime < since:
                continue
            if until is not None and line_datetime > until:
                continue
            filtered.append(line)
        lines = tuple(filtered)

    if not lines:
        msg = f"no lines available in selected time window from {path}"
        raise ValueError(msg)

    start = _extract_datetime(lines[0])
    end = _extract_datetime(lines[-1])
    return LogWindow(lines=lines, start=start, end=end)


def _extract_request_path(line: str) -> str:
    match = REQUEST_RE.search(line)
    if match is None:
        return ""
    return match.group("path")


def _extract_latency_ms(line: str) -> float | None:
    last_field = line.rsplit(maxsplit=1)[-1]
    if last_field == "-":
        return None
    try:
        return float(last_field)
    except ValueError:
        return None


def _route_stats(route: str, lines: list[str]) -> RouteStat | None:
    latencies = [
        value
        for value in (_extract_latency_ms(line) for line in lines)
        if value is not None
    ]
    if not latencies:
        return None

    total = sum(latencies)
    calls = len(latencies)
    return RouteStat(
        route=route,
        calls=calls,
        total=total,
        average=total / calls,
        minimum=min(latencies),
        maximum=max(latencies),
        maxcount=sum(1 for value in latencies if value > MAXCOUNT_THRESHOLD),
    )


def _discover_fastapi_routes() -> list[str]:
    server_dir = _server_dir()
    sys.path.insert(0, str(server_dir))

    apiroute = importlib.import_module("fastapi.routing").APIRoute
    create_app = importlib.import_module("fishtest.app").create_app
    app = create_app()

    paths = {
        (route.path.split("{", maxsplit=1)[0].rstrip("/") or "/")
        for route in app.routes
        if isinstance(route, apiroute)
    }
    return sorted(paths, key=lambda path: (len(path), path), reverse=True)


def _stdout(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _stderr(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def _analyze_routes(lines: tuple[str, ...], routes: list[str]) -> list[RouteStat]:
    remaining = list(lines)
    results: list[RouteStat] = []

    for route in routes:
        matched: list[str] = []
        kept: list[str] = []
        for line in remaining:
            path = _extract_request_path(line)
            if path.startswith(route):
                matched.append(line)
            else:
                kept.append(line)
        remaining = kept

        stat = _route_stats(route, matched)
        if stat is not None:
            results.append(stat)

    return sorted(results, key=lambda stat: stat.total, reverse=True)


def _print_summary(window: LogWindow) -> None:
    duration = int((window.end - window.start).total_seconds())
    dropped = sum(1 for line in window.lines if line.rsplit(maxsplit=1)[-1] == "-")
    handled = len(window.lines) - dropped
    rate = "N/A" if duration == 0 else f"{len(window.lines) / duration:.2f}"

    _stdout(
        "# logging from "
        f"[{window.start:%d/%b/%Y:%H:%M:%S %z}] to "
        f"[{window.end:%d/%b/%Y:%H:%M:%S %z}]",
    )
    _stdout(f"# duration (seconds)            : {duration}")
    _stdout(f"# calls in total                : {len(window.lines)}")
    _stdout(f"# calls per second              : {rate}")
    _stdout(f"# calls not reaching the backend: {dropped}")
    _stdout(f"# calls handled by the backend  : {handled}")


def _print_route_table(stats: list[RouteStat]) -> None:
    _stdout(
        f"#{'route':>30} {'calls':>8} {'total':>10} {'average':>10}"
        f" {'minimum':>10} {'maximum':>10} {'maxcount':>8}",
    )
    for stat in stats:
        _stdout(
            f" {stat.route:>30} {stat.calls:8d} {stat.total:10.3f} {stat.average:10.3f}"
            f" {stat.minimum:10.3f} {stat.maximum:10.3f} {stat.maxcount:8d}",
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    default_log_file: Path = Path("/var/log/nginx/access.log"),
) -> int:
    """Run access log analysis and print aggregated metrics."""
    args = _parse_args(argv, default_log_file=default_log_file)

    try:
        window = _read_log_window(
            args.log_file,
            since=args.since,
            until=args.until,
        )
    except PermissionError as exc:
        _stderr(
            f"Error: {exc}. The log file may require root access; "
            "try running with sudo.",
        )
        return 1
    except (OSError, ValueError) as exc:
        _stderr(f"Error: {exc}")
        return 1

    try:
        routes = _discover_fastapi_routes()
    except Exception as exc:  # noqa: BLE001
        _stderr(f"Error: failed to discover FastAPI routes: {exc}")
        return 1

    if not routes:
        _stderr("Error: no routes discovered from FastAPI app.")
        return 1

    _print_summary(window)
    stats = _analyze_routes(window.lines, routes)
    _print_route_table(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
