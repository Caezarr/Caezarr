#!/usr/bin/env python3
"""Generate the profile README's self-hosted contribution sparkline."""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


API = "https://api.github.com/graphql"
WIDTH = 760
HEIGHT = 158
PLOT_LEFT = 77
PLOT_RIGHT = 695

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
  }
}
"""


def contribution_window() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    return (
        f"{start.isoformat()}T00:00:00Z",
        f"{today.isoformat()}T23:59:59Z",
    )


def fetch_calendar(login: str, token: str) -> dict:
    start, end = contribution_window()
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {"login": login, "from": start, "to": end},
        }
    ).encode()
    request = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-contributions",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise SystemExit(f"GitHub GraphQL error: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise SystemExit(f"GitHub user not found: {login}")
    return user["contributionsCollection"]["contributionCalendar"]


def text(
    x: float,
    y: float,
    value: object,
    css: str,
    size: int,
    anchor: str = "start",
    weight: int = 400,
) -> str:
    safe = html.escape(str(value))
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css}" '
        f'font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}">{safe}</text>'
    )


def make_svg(calendar: dict) -> str:
    weeks = calendar["weeks"]
    weekly = [
        sum(day["contributionCount"] for day in week["contributionDays"])
        for week in weeks
    ]
    days = [day for week in weeks for day in week["contributionDays"]]
    total = calendar["totalContributions"]
    active = sum(day["contributionCount"] > 0 for day in days)
    best_week = max(weekly, default=0)

    base_y = 148
    top_y = 99
    peak = max(weekly, default=1) or 1
    step = (PLOT_RIGHT - PLOT_LEFT) / max(len(weekly) - 1, 1)
    points = [
        (PLOT_LEFT + index * step, base_y - (value / peak) * (base_y - top_y))
        for index, value in enumerate(weekly)
    ]
    if not points:
        points = [
            (float(PLOT_LEFT), float(base_y)),
            (float(PLOT_RIGHT), float(base_y)),
        ]

    line_path = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    area_path = (
        f"M{points[0][0]:.1f} {base_y:.1f}"
        + "".join(f"L{x:.1f} {y:.1f}" for x, y in points)
        + f"L{points[-1][0]:.1f} {base_y:.1f}Z"
    )

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
            f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
            'role="img" aria-labelledby="title desc" '
            'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'
            '&apos;Liberation Mono&apos;,monospace">'
        ),
        "<title id=\"title\">Gabriel Rance GitHub contribution activity</title>",
        (
            f'<desc id="desc">{total} contributions across {active} active '
            f'days during the last year; best week: {best_week}.</desc>'
        ),
        (
            "<style>"
            ".strong{fill:#424a53}.ink{fill:#6e7681}.muted{fill:#8c959f}"
            ".line{fill:none;stroke:#6e7681}.area{fill:#6e7681;opacity:.13}"
            ".dot{fill:#424a53;stroke:#fff}"
            "@media(prefers-color-scheme:dark){"
            ".strong{fill:#f0f6fc}.ink{fill:#c9d1d9}.muted{fill:#8b949e}"
            ".line{stroke:#c9d1d9}.area{fill:#c9d1d9;opacity:.16}"
            ".dot{fill:#f0f6fc;stroke:#0d1117}}"
            "</style>"
        ),
        text(PLOT_LEFT, 59, total, "strong", 52, weight=600),
        text(PLOT_LEFT, 81, "contributions in the last year", "muted", 12),
        text(PLOT_RIGHT, 39, active, "strong", 19, anchor="end", weight=600),
        text(PLOT_RIGHT, 56, "active days", "muted", 11, anchor="end"),
        text(PLOT_RIGHT, 79, best_week, "strong", 19, anchor="end", weight=600),
        text(PLOT_RIGHT, 96, "best week", "muted", 11, anchor="end"),
        f'<path d="{area_path}" class="area"/>',
        (
            f'<path d="{line_path}" class="line" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        ),
        (
            f'<circle cx="{points[-1][0] - 2:.1f}" cy="{points[-1][1]:.1f}" '
            'r="4.5" class="dot" stroke-width="2"/>'
        ),
        "</svg>",
    ]
    return "".join(parts)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    login = os.environ.get("GH_LOGIN", "Caezarr")
    output = Path(os.environ.get("OUTPUT", "contributions.svg"))
    svg = make_svg(fetch_calendar(login, token))
    if output.exists() and output.read_text(encoding="utf-8") == svg:
        print(f"{output}: unchanged")
        return
    output.write_text(svg, encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
