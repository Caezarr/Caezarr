#!/usr/bin/env python3
"""Generate a self-hosted contribution graph for the profile README."""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


API = "https://api.github.com/graphql"
WIDTH = 620
HEIGHT = 194
LEFT = 34
TOP = 104
CELL_X = 10.7
CELL_Y = 11.2
RAMP = ("·", ":", "+", "#", "@")
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec")

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
            weekday
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


def flatten_days(weeks: list[dict]) -> list[dict]:
    return [day for week in weeks for day in week["contributionDays"]]


def streaks(days: list[dict]) -> tuple[int, int]:
    longest = 0
    running = 0
    for day in days:
        if day["contributionCount"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    # Today may still be empty without ending the current streak.
    relevant = days[:-1] if days and days[-1]["contributionCount"] == 0 else days
    current = 0
    for day in reversed(relevant):
        if day["contributionCount"] == 0:
            break
        current += 1
    return current, longest


def intensity(value: int) -> int:
    if value <= 0:
        return 0
    if value <= 2:
        return 1
    if value <= 5:
        return 2
    if value <= 9:
        return 3
    return 4


def label(x: float, y: float, text: str, css: str, size: int,
          anchor: str = "start", weight: int = 400) -> str:
    safe = html.escape(str(text))
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css}" '
        f'font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}">{safe}</text>'
    )


def make_svg(calendar: dict) -> str:
    weeks = calendar["weeks"]
    days = flatten_days(weeks)
    total = calendar["totalContributions"]
    active = sum(day["contributionCount"] > 0 for day in days)
    current, longest = streaks(days)

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
            f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
            'role="img" aria-labelledby="title desc" '
            'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'
            '&apos;Liberation Mono&apos;,monospace">'
        ),
        "<title id=\"title\">Gabriel Rance GitHub contributions</title>",
        (
            f'<desc id="desc">{total} contributions across {active} active '
            f'days during the last year.</desc>'
        ),
        (
            "<style>"
            ".strong{fill:#24292f}.ink{fill:#57606a}.muted{fill:#8c959f}"
            ".rule{stroke:#d0d7de}.l0{fill:#d8dee4}.l1{fill:#9ba4ae}"
            ".l2{fill:#6e7781}.l3{fill:#424a53}.l4{fill:#1f2328}"
            "@media(prefers-color-scheme:dark){"
            ".strong{fill:#f0f6fc}.ink{fill:#b1bac4}.muted{fill:#8b949e}"
            ".rule{stroke:#30363d}.l0{fill:#30363d}.l1{fill:#57606a}"
            ".l2{fill:#8b949e}.l3{fill:#c9d1d9}.l4{fill:#f0f6fc}}"
            "</style>"
        ),
        label(0, 16, "CONTRIBUTIONS / LAST 365 DAYS", "muted", 9),
        label(0, 61, str(total), "strong", 42, weight=600),
        label(0, 80, "contributions", "muted", 11),
        label(255, 49, str(active), "strong", 20, anchor="middle", weight=600),
        label(255, 68, "active days", "muted", 10, anchor="middle"),
        label(405, 49, str(current), "strong", 20, anchor="middle", weight=600),
        label(405, 68, "current streak", "muted", 10, anchor="middle"),
        label(555, 49, str(longest), "strong", 20, anchor="middle", weight=600),
        label(555, 68, "longest streak", "muted", 10, anchor="middle"),
        '<line x1="0" y1="90.5" x2="620" y2="90.5" class="rule"/>',
    ]

    for weekday, name in ((1, "mon"), (3, "wed"), (5, "fri")):
        y = TOP + weekday * CELL_Y + 8
        parts.append(label(LEFT - 8, y, name, "muted", 8, anchor="end"))

    last_month = None
    last_label_x = -100.0
    for week_index, week in enumerate(weeks):
        if not week["contributionDays"]:
            continue
        x = LEFT + week_index * CELL_X
        month = date.fromisoformat(week["contributionDays"][0]["date"]).month
        if month != last_month and x - last_label_x >= 32:
            parts.append(label(x, TOP - 7, MONTHS[month - 1], "muted", 8))
            last_label_x = x
        last_month = month

        by_weekday = {
            day["weekday"]: day for day in week["contributionDays"]
        }
        for weekday in range(7):
            day = by_weekday.get(weekday)
            if not day:
                continue
            y = TOP + weekday * CELL_Y
            level = intensity(day["contributionCount"])
            character = RAMP[level]
            tooltip = html.escape(
                f"{day['date']}: {day['contributionCount']} contributions"
            )
            parts.append(
                f'<g><title>{tooltip}</title>'
                f'<text x="{x:.1f}" y="{y + 8:.1f}" class="l{level}" '
                f'font-size="10">{character}</text></g>'
            )

    parts.extend(
        [
            label(LEFT, 190, "quiet", "muted", 8),
            label(WIDTH - 4, 190, "loud", "muted", 8, anchor="end"),
            label(WIDTH / 2, 190, "·  :  +  #  @", "ink", 9, anchor="middle"),
            "</svg>",
        ]
    )
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
