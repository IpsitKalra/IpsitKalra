#!/usr/bin/env python3
"""Generate light and dark SVG mission-control cards for a GitHub profile.

Uses Python's standard library, GitHub's REST API, an editable TELEMETRY.json,
and optionally Anthropic's organization Usage API.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
NOW_FILE = ROOT / "NOW.md"
TELEMETRY_FILE = ROOT / "TELEMETRY.json"
GITHUB_API = "https://api.github.com"
ANTHROPIC_USAGE_API = "https://api.anthropic.com/v1/organizations/usage_report/messages"

DEFAULT_METRICS = [
    {
        "label": "CLAUDE TOKENS SACRIFICED",
        "value": "2.7M",
        "detail": "this month · probably worth it",
    },
    {
        "label": '"QUICK FIXES" ATTEMPTED',
        "value": "14",
        "detail": "0 remained quick",
    },
    {
        "label": "BUGS PROMOTED TO FEATURES",
        "value": "06",
        "detail": "marketing approved",
    },
]
DEFAULT_STATUS = "CURRENT SANITY: CACHED · COFFEE-to-COMMIT LATENCY: 11m"


def github_json(path: str, token: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-mission-control",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{GITHUB_API}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def read_transmission() -> str:
    if not NOW_FILE.exists():
        return "Building useful things with unusual care."
    for raw_line in NOW_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith(("#", "<!--")):
            return line[:88]
    return "Building useful things with unusual care."


def clean_metric(metric: Any, fallback: dict[str, str]) -> dict[str, str]:
    if not isinstance(metric, dict):
        return fallback.copy()
    return {
        "label": str(metric.get("label") or fallback["label"])[:26],
        "value": str(metric.get("value") or fallback["value"])[:14],
        "detail": str(metric.get("detail") or fallback["detail"])[:32],
    }


def load_telemetry() -> tuple[list[dict[str, str]], str]:
    payload: dict[str, Any] = {}
    if TELEMETRY_FILE.exists():
        try:
            loaded = json.loads(TELEMETRY_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError as exc:
            print(f"warning: invalid TELEMETRY.json ({exc}); using defaults")

    raw_metrics = payload.get("metrics")
    if not isinstance(raw_metrics, list):
        raw_metrics = []

    metrics = []
    for index, fallback in enumerate(DEFAULT_METRICS):
        metric = raw_metrics[index] if index < len(raw_metrics) else fallback
        metrics.append(clean_metric(metric, fallback))

    status = str(payload.get("status_line") or DEFAULT_STATUS)[:72]
    return metrics, status


def load_identity() -> dict[str, Any]:
    """Optional name/bio/stack overrides from TELEMETRY.json.

    Lets the card show a real display name even when the GitHub profile
    leaves the name field blank, and a curated stack instead of the raw
    language mix inferred from repositories. Empty values fall back.
    """
    empty: dict[str, Any] = {"name": "", "bio": "", "stack": []}
    if not TELEMETRY_FILE.exists():
        return empty
    try:
        loaded = json.loads(TELEMETRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty
    if not isinstance(loaded, dict):
        return empty
    raw_stack = loaded.get("stack")
    stack = [str(item)[:16] for item in raw_stack if item][:6] if isinstance(raw_stack, list) else []
    return {
        "name": str(loaded.get("name") or "")[:40],
        "bio": str(loaded.get("bio") or "")[:96],
        "stack": stack,
    }


def format_compact(value: int) -> str:
    if value < 1_000:
        return str(value)
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= divisor:
            compact = value / divisor
            digits = 0 if compact >= 100 else 1
            return f"{compact:.{digits}f}".rstrip("0").rstrip(".") + suffix
    return str(value)


def anthropic_tokens_this_month(admin_key: str) -> int | None:
    """Return organization API tokens used this UTC month, when available.

    This endpoint requires an Anthropic Admin API key. It does not read a
    personal Claude subscription's private usage history.
    """
    if not admin_key:
        return None

    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query = urllib.parse.urlencode(
        {
            "starting_at": start.isoformat().replace("+00:00", "Z"),
            "ending_at": now.isoformat().replace("+00:00", "Z"),
            "bucket_width": "1d",
            "limit": 31,
        }
    )
    request = urllib.request.Request(
        f"{ANTHROPIC_USAGE_API}?{query}",
        headers={
            "anthropic-version": "2023-06-01",
            "x-api-key": admin_key,
            "content-type": "application/json",
            "User-Agent": "profile-mission-control",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"warning: Anthropic Usage API unavailable ({exc}); using TELEMETRY.json")
        return None

    total = 0
    for bucket in payload.get("data", []):
        for result in bucket.get("results", []):
            total += int(result.get("uncached_input_tokens") or 0)
            total += int(result.get("cache_read_input_tokens") or 0)
            total += int(result.get("output_tokens") or 0)
            total += int(result.get("cache_creation_input_tokens") or 0)
            cache_creation = result.get("cache_creation") or {}
            if isinstance(cache_creation, dict):
                total += int(cache_creation.get("ephemeral_1h_input_tokens") or 0)
                total += int(cache_creation.get("ephemeral_5m_input_tokens") or 0)
    return total


def get_data(username: str, github_token: str, anthropic_admin_key: str) -> dict[str, Any]:
    metrics, status_line = load_telemetry()
    identity = load_identity()
    live_tokens = anthropic_tokens_this_month(anthropic_admin_key)
    if live_tokens is not None:
        metrics[0] = {
            "label": "CLAUDE TOKENS SACRIFICED",
            "value": format_compact(live_tokens),
            "detail": "this UTC month · live org usage",
        }

    try:
        user = github_json(f"/users/{username}", github_token)
        repos = github_json(
            f"/users/{username}/repos?type=owner&sort=pushed&direction=desc&per_page=100",
            github_token,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"warning: GitHub API unavailable ({exc}); generating a fallback card")
        user, repos = {}, []

    owned = [repo for repo in repos if not repo.get("fork") and not repo.get("archived")]
    active = owned[:3]
    languages = Counter(repo.get("language") for repo in owned if repo.get("language"))

    return {
        "name": identity["name"] or user.get("name") or username,
        "username": username,
        "bio": (identity["bio"] or user.get("bio") or "Building software, systems, and useful experiments.")[:96],
        "active": [repo.get("name", "unknown") for repo in active],
        "languages": identity["stack"] or [name for name, _ in languages.most_common(3)],
        "metrics": metrics,
        "status_line": status_line,
        "transmission": read_transmission(),
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def deterministic_points(username: str, count: int = 16) -> list[tuple[int, int, int]]:
    digest = hashlib.sha256(username.encode("utf-8")).digest()
    points: list[tuple[int, int, int]] = []
    for index in range(count):
        a = digest[(index * 2) % len(digest)]
        b = digest[(index * 2 + 1) % len(digest)]
        radius = 22 + (a % 95)
        angle = (b / 255) * math.tau
        x = int(162 + radius * math.cos(angle))
        y = int(178 + radius * math.sin(angle))
        size = 2 + (a % 3)
        points.append((x, y, size))
    return points


def safe(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fit(items: list[str], fallback: str) -> str:
    text = "  ·  ".join(items) if items else fallback
    return text[:62]


def wrap_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    """Greedily wrap text into up to max_lines lines, ellipsizing any overflow.

    SVG <text> does not wrap on its own, so long strings must be split into
    separate lines by hand.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max_chars - 1].rstrip() + "…"
    return lines or [""]


def render_metric(metric: dict[str, str], x: int, width: int, bg: str, grid: str, muted: str, text: str) -> str:
    return f'''
  <rect x="{x}" y="145" width="{width}" height="68" rx="11" fill="{bg}" stroke="{grid}"/>
  <text x="{x + 14}" y="166" fill="{muted}" font-size="9.5" letter-spacing="0.6">{safe(metric['label'])}</text>
  <text x="{x + 14}" y="192" fill="{text}" font-size="21" font-weight="700">{safe(metric['value'])}</text>
  <text x="{x + 14}" y="207" fill="{muted}" font-size="8.5">{safe(metric['detail'])}</text>'''


def render_svg(data: dict[str, Any], mode: str) -> str:
    dark = mode == "dark"
    bg = "#0d1117" if dark else "#f6f8fa"
    panel = "#161b22" if dark else "#ffffff"
    text = "#f0f6fc" if dark else "#1f2328"
    muted = "#8b949e" if dark else "#656d76"
    grid = "#30363d" if dark else "#d8dee4"
    accent = "#7ee787" if dark else "#1a7f37"
    accent2 = "#79c0ff" if dark else "#0969da"
    warning = "#e3b341" if dark else "#9a6700"

    points = "\n".join(
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{accent2}" opacity="0.75">'
        f'<animate attributeName="opacity" values="0.25;0.95;0.25" dur="{3 + (x % 5)}s" '
        f'begin="{(y % 9) / 3:.1f}s" repeatCount="indefinite"/></circle>'
        for x, y, r in deterministic_points(data["username"])
    )

    active = fit(data["active"], "No public active repositories detected")
    languages = " · ".join(data["languages"])[:54] if data["languages"] else "Language signals pending"
    metrics = data["metrics"]

    transmission_lines = wrap_lines(data["transmission"], 68, 2)
    signal = []
    y = 242
    signal.append(f'<text x="326" y="{y}" fill="{accent2}" font-size="12" letter-spacing="1.5">CURRENT TRANSMISSION</text>')
    y += 21
    for line in transmission_lines:
        signal.append(f'<text x="326" y="{y}" fill="{text}" font-size="14">{safe(line)}</text>')
        y += 19
    y += 12
    signal.append(f'<text x="326" y="{y}" fill="{accent2}" font-size="12" letter-spacing="1.5">ACTIVE REPOSITORIES</text>')
    y += 21
    signal.append(f'<text x="326" y="{y}" fill="{text}" font-size="14">{safe(active)}</text>')
    y += 26
    signal.append(f'<text x="326" y="{y}" fill="{warning}" font-size="11">{safe(data["status_line"])}</text>')
    y += 21
    signal.append(f'<text x="326" y="{y}" fill="{muted}" font-size="11">LANGUAGE SIGNALS  {safe(languages)}</text>')
    signal.append(f'<text x="932" y="{y}" text-anchor="end" fill="{muted}" font-size="10">REFRESHED {safe(data["updated"])}</text>')
    signal_lines = "\n  ".join(signal)
    metric_cards = "".join(
        (
            render_metric(metrics[0], 326, 194, bg, grid, muted, text),
            render_metric(metrics[1], 532, 194, bg, grid, muted, text),
            render_metric(metrics[2], 738, 194, bg, grid, muted, text),
        )
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="980" height="410" viewBox="0 0 980 410" role="img" aria-labelledby="title desc">
<title id="title">Mission control dashboard for {safe(data['name'])}</title>
<desc id="desc">A live developer telemetry panel showing personalized metrics, current work, active repositories, languages, and refresh time.</desc>
<defs>
  <linearGradient id="frame" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{accent2}" stop-opacity="0.75"/>
    <stop offset="0.55" stop-color="{accent}" stop-opacity="0.2"/>
    <stop offset="1" stop-color="{warning}" stop-opacity="0.65"/>
  </linearGradient>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3" result="blur"/>
    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <pattern id="microgrid" width="24" height="24" patternUnits="userSpaceOnUse">
    <path d="M 24 0 L 0 0 0 24" fill="none" stroke="{grid}" stroke-width="0.6" opacity="0.45"/>
  </pattern>
</defs>

<rect width="980" height="410" rx="22" fill="{bg}"/>
<rect x="1" y="1" width="978" height="408" rx="21" fill="none" stroke="url(#frame)" stroke-width="2"/>
<rect x="18" y="18" width="944" height="374" rx="16" fill="{panel}"/>
<rect x="18" y="18" width="944" height="374" rx="16" fill="url(#microgrid)"/>

<!-- Radar -->
<g>
  <circle cx="162" cy="188" r="120" fill="none" stroke="{grid}" stroke-width="1"/>
  <circle cx="162" cy="188" r="86" fill="none" stroke="{grid}" stroke-width="1"/>
  <circle cx="162" cy="188" r="51" fill="none" stroke="{grid}" stroke-width="1"/>
  <line x1="42" y1="188" x2="282" y2="188" stroke="{grid}" opacity="0.75"/>
  <line x1="162" y1="68" x2="162" y2="308" stroke="{grid}" opacity="0.75"/>
  <g transform="translate(0 10)">
    <circle cx="162" cy="178" r="107" fill="none" stroke="{accent}" stroke-width="3" stroke-dasharray="9 15" opacity="0.65">
      <animateTransform attributeName="transform" type="rotate" from="0 162 178" to="360 162 178" dur="18s" repeatCount="indefinite"/>
    </circle>
    <path d="M162 178 L162 70 A108 108 0 0 1 257 127 Z" fill="{accent2}" opacity="0.11">
      <animateTransform attributeName="transform" type="rotate" from="0 162 178" to="360 162 178" dur="7s" repeatCount="indefinite"/>
    </path>
    <line x1="162" y1="178" x2="162" y2="70" stroke="{accent2}" stroke-width="2" opacity="0.9" filter="url(#glow)">
      <animateTransform attributeName="transform" type="rotate" from="0 162 178" to="360 162 178" dur="7s" repeatCount="indefinite"/>
    </line>
    {points}
    <circle cx="162" cy="178" r="6" fill="{accent}" filter="url(#glow)"/>
  </g>
  <text x="162" y="344" text-anchor="middle" fill="{muted}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" letter-spacing="2">CHAOS SIGNAL RADAR</text>
</g>

<!-- Header -->
<text x="326" y="63" fill="{muted}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" letter-spacing="2.2">MISSION CONTROL // {safe(data['username']).upper()}</text>
<text x="326" y="100" fill="{text}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="28" font-weight="700">{safe(data['name'])}</text>
<circle cx="930" cy="57" r="5" fill="{accent}" filter="url(#glow)">
  <animate attributeName="opacity" values="0.35;1;0.35" dur="2s" repeatCount="indefinite"/>
</circle>
<text x="916" y="62" text-anchor="end" fill="{accent}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" letter-spacing="1.5">ONLINE-ISH</text>
<text x="326" y="126" fill="{muted}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="15">{safe(data['bio'])}</text>

<!-- Questionable telemetry -->
<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  {metric_cards}
</g>

<!-- Signal lines -->
<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  {signal_lines}
</g>
</svg>'''


def main() -> None:
    username = os.environ.get("PROFILE_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "YOUR_USERNAME"
    github_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    anthropic_admin_key = os.environ.get("ANTHROPIC_ADMIN_KEY") or ""
    ASSETS.mkdir(parents=True, exist_ok=True)
    data = get_data(username, github_token, anthropic_admin_key)

    if username == "YOUR_USERNAME" and not github_token:
        data.update(
            {
                "name": "YOUR NAME",
                "bio": "Builder of thoughtful systems, useful tools, and ambitious experiments.",
                "active": ["project-alpha", "project-orbit", "project-signal"],
                "languages": ["TypeScript", "Python", "YOUR_STACK"],
            }
        )

    for mode in ("light", "dark"):
        output = ASSETS / f"mission-control-{mode}.svg"
        output.write_text(render_svg(data, mode), encoding="utf-8")
        print(f"wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
