#!/usr/bin/env python3
"""
Dynamic GitHub Contributions Graph Generator
Generates a dark-themed SVG contributions graph matching GitHub's dark UI,
featuring a 31-day daily contributions line chart, a full-year heatmap,
and an activity progress bar.

Author: Prashant Vala (valaprashant97)
"""

import os
import sys
import re
import json
import argparse
import urllib.request
from datetime import datetime


def fetch_contributions_graphql(username, token):
    """Fetch contribution history using GitHub GraphQL API."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                contributionLevel
                weekday
              }
            }
          }
        }
      }
    }
    """
    level_map = {
        "NONE": 0,
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4
    }

    req_data = json.dumps({"query": query, "variables": {"login": username}}).encode('utf-8')
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=req_data,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "GitHub-Contributions-Graph-Generator",
            "Content-Type": "application/json"
        }
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        if "data" in res and res["data"] and res["data"].get("user"):
            cal = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            days = []
            for week in cal.get("weeks", []):
                for d in week.get("contributionDays", []):
                    days.append({
                        "date": d["date"],
                        "count": int(d["contributionCount"]),
                        "level": level_map.get(d["contributionLevel"], 0),
                        "weekday": int(d.get("weekday", 0))
                    })
            total = cal.get("totalContributions", sum(d["count"] for d in days))
            return days, total
        else:
            errors = res.get("errors", [])
            raise ValueError(f"GraphQL error: {errors}")


def fetch_contributions_public(username):
    """Fetch and parse contribution history from GitHub's public contribution calendar page."""
    url = f"https://github.com/users/{username}/contributions"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode('utf-8')

    td_pattern = re.compile(r'<td\b([^>]*)>', re.IGNORECASE)
    attr_pattern = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')

    tooltips_raw = re.findall(r'<tool-tip\b([^>]*)>(.*?)</tool-tip>', html, re.DOTALL | re.IGNORECASE)
    tooltips = {}
    for attrs_str, content in tooltips_raw:
        attrs = dict(attr_pattern.findall(attrs_str))
        for_id = attrs.get('for')
        if for_id:
            tooltips[for_id] = content.strip()

    days = []
    for m in td_pattern.finditer(html):
        attrs_str = m.group(1)
        attrs = dict(attr_pattern.findall(attrs_str))
        if 'ContributionCalendar-day' in attrs.get('class', ''):
            day_id = attrs.get('id', '')
            date_str = attrs.get('data-date', '')
            level = int(attrs.get('data-level', '0'))
            tt = tooltips.get(day_id, '')

            count = 0
            cm = re.search(r'(\d+)\s+contribution', tt)
            if cm:
                count = int(cm.group(1))
            elif level > 0:
                count = level

            if date_str:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                weekday = (dt.weekday() + 1) % 7 # 0 = Sun .. 6 = Sat
                days.append({
                    "date": date_str,
                    "count": count,
                    "level": level,
                    "weekday": weekday
                })

    days.sort(key=lambda d: d["date"])
    total = sum(d["count"] for d in days)
    return days, total


def get_contributions(username, token=None):
    """Retrieve contribution data via GraphQL (if token available) or public endpoint fallback."""
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        try:
            print("Attempting to fetch contribution data via GitHub GraphQL API...")
            days, total = fetch_contributions_graphql(username, token)
            print(f"GraphQL fetch succeeded: {len(days)} days, {total} total contributions.")
            return days, total
        except Exception as e:
            print(f"GraphQL fetch failed ({e}). Falling back to public endpoint...")

    print(f"Fetching public contribution calendar for @{username}...")
    days, total = fetch_contributions_public(username)
    print(f"Public fetch succeeded: {len(days)} days, {total} total contributions.")
    return days, total


def generate_svg(days, total_contributions):
    """
    Generate an SVG contributions graph matching the reference dark design:
    - Dimensions: 757 x 459 (viewBox 0 0 757 459, responsive 100%)
    - Background: #0d1117 (GitHub Dark), Border: #30363d
    - Header: Teal curved loop icon and 'Contributions' text
    - Line Chart: Last 31 days with blue curve, blue dots, dynamic Y scale, vertical gridlines
    - Heatmap: 53 calendar weeks with purple/violet intensity levels
    - Bottom Activity Bar: Gradient progress/activity bar with emerald-to-neon green segments
    """
    W = 757
    H = 459

    # 1. Line Chart Data (Last 31 days)
    days_31 = days[-31:] if len(days) >= 31 else days
    counts_31 = [d["count"] for d in days_31]
    max_count = max(counts_31) if counts_31 else 1

    # Calculate dynamic Y-axis ceiling
    if max_count <= 2:
        y_max = max_count if max_count > 0 else 1
        y_ticks = [0, y_max]
    elif max_count <= 10:
        y_max = max_count
        y_ticks = [0, max_count // 2, max_count]
    else:
        step = 10 if max_count >= 30 else 5
        y_max = ((max_count + step - 1) // step) * step
        y_ticks = [0, y_max // 2, y_max]

    chart_x_start = 82
    chart_x_end = 698
    chart_y_top = 93
    chart_y_base = 249
    chart_height = chart_y_base - chart_y_top

    num_points = len(days_31)
    x_step = (chart_x_end - chart_x_start) / (num_points - 1) if num_points > 1 else 0

    chart_points = []
    vertical_grid_lines = []
    x_labels = []

    for i, d in enumerate(days_31):
        x = chart_x_start + i * x_step
        count = d["count"]
        y = chart_y_base - (count / y_max) * chart_height
        chart_points.append((x, y, count, d["date"]))

        # Vertical dashed grid line
        vertical_grid_lines.append(
            f'<line x1="{x:.1f}" y1="{chart_y_top}" x2="{x:.1f}" y2="{chart_y_base}" stroke="#21262d" stroke-dasharray="2,3" stroke-width="1"/>'
        )

        # Day label (day of month)
        day_num = str(int(d["date"].split("-")[2]))
        x_labels.append(
            f'<text x="{x:.1f}" y="265" text-anchor="middle" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11" font-weight="500">{day_num}</text>'
        )

    # Gradient area under curve
    area_d = [f"M {chart_points[0][0]:.1f} {chart_y_base}"]
    for x, y, _, _ in chart_points:
        area_d.append(f"L {x:.1f} {y:.1f}")
    area_d.append(f"L {chart_points[-1][0]:.1f} {chart_y_base} Z")
    area_str = " ".join(area_d)

    # Blue line plot
    line_d = [f"M {chart_points[0][0]:.1f} {chart_points[0][1]:.1f}"]
    for x, y, _, _ in chart_points[1:]:
        line_d.append(f"L {x:.1f} {y:.1f}")
    line_str = " ".join(line_d)

    # Blue dots
    blue_dots = []
    for (x, y, count, date_str) in chart_points:
        blue_dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#58a6ff" stroke="#0d1117" stroke-width="1">'
            f'<title>{date_str}: {count} contribution{"s" if count != 1 else ""}</title>'
            f'</circle>'
        )

    # Y-axis ticks and horizontal grid lines
    y_axis_elements = []
    for val in y_ticks:
        y_pos = chart_y_base - (val / y_max) * chart_height
        y_axis_elements.append(
            f'<text x="{chart_x_start - 10}" y="{y_pos + 4:.1f}" text-anchor="end" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11" font-weight="500">{val}</text>'
        )
        if val > 0:
            y_axis_elements.append(
                f'<line x1="{chart_x_start}" y1="{y_pos:.1f}" x2="{chart_x_end}" y2="{y_pos:.1f}" stroke="#30363d" stroke-dasharray="2,3" stroke-width="1"/>'
            )

    # 2. Heatmap Grid (53 weeks)
    weeks = []
    current_week = [None] * 7
    for d in days:
        w_day = d["weekday"]
        if w_day == 0 and any(x is not None for x in current_week):
            weeks.append(current_week)
            current_week = [None] * 7
        current_week[w_day] = d
    if any(x is not None for x in current_week):
        weeks.append(current_week)

    # Keep 53 weeks to span calendar
    if len(weeks) > 53:
        weeks = weeks[-53:]

    hm_start_x = 42
    hm_col_step = (712 - hm_start_x - 10.2) / (len(weeks) - 1) if len(weeks) > 1 else 12.6
    hm_start_y = 321
    hm_row_step = 12.6
    cell_size = 10.2

    # Purple/violet theme matching reference image
    colors = {
        0: "#161b22",
        1: "#581c87",
        2: "#7e22ce",
        3: "#a855f7",
        4: "#d8b4fe"
    }

    heatmap_rects = []
    week_activity = []

    for col_idx, week in enumerate(weeks):
        col_x = hm_start_x + col_idx * hm_col_step
        col_total = 0
        for row_idx, day_obj in enumerate(week):
            row_y = hm_start_y + row_idx * hm_row_step
            if day_obj is not None:
                lvl = day_obj["level"]
                col_total += day_obj["count"]
                fill_color = colors.get(lvl, colors[0])
                tooltip_text = f"{day_obj['date']}: {day_obj['count']} contributions"
                heatmap_rects.append(
                    f'<rect x="{col_x:.1f}" y="{row_y:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" rx="2" ry="2" fill="{fill_color}">'
                    f'<title>{tooltip_text}</title>'
                    f'</rect>'
                )
        week_activity.append(col_total)

    # 3. Bottom Activity / Progress Bar
    bar_x = hm_start_x
    bar_w = (hm_start_x + (len(weeks) - 1) * hm_col_step + cell_size) - bar_x
    bar_y = 435
    bar_h = 9
    bar_rx = 4.5

    bar_segments = []
    for i, act in enumerate(week_activity):
        seg_x = hm_start_x + i * hm_col_step
        seg_w = cell_size
        if act == 0:
            continue
        elif act < 5:
            seg_color = "#034525"
        elif act < 15:
            seg_color = "#0e6235"
        elif act < 30:
            seg_color = "#15803d"
        elif act < 60:
            seg_color = "#22c55e"
        else:
            seg_color = "#00e676"

        bar_segments.append(
            f'<rect x="{seg_x:.1f}" y="{bar_y}" width="{seg_w:.1f}" height="{bar_h}" fill="{seg_color}"/>'
        )

    # Assemble complete SVG
    svg = f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#388bfd" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#388bfd" stop-opacity="0.0"/>
    </linearGradient>
    <clipPath id="bar-clip">
      <rect x="{bar_x:.1f}" y="{bar_y}" width="{bar_w:.1f}" height="{bar_h}" rx="{bar_rx}" ry="{bar_rx}" />
    </clipPath>
  </defs>

  <!-- Background Card -->
  <rect x="8" y="8" width="{W - 16}" height="{H - 16}" rx="8" ry="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>

  <!-- Header Divider -->
  <line x1="8" y1="36" x2="{W - 8}" y2="36" stroke="#21262d" stroke-width="1"/>

  <!-- Header Icon (Teal/Mint Loop Icon) -->
  <g transform="translate(24, 11)">
    <path d="M 14.5 4 C 18 4, 21 6.5, 21 10 C 21 13.5, 18 16, 14.5 16 C 11.5 16, 9.5 14, 8 11.5 C 6.5 9, 4.5 7, 2.5 7 C 1 7, 0 8, 0 9.5 C 0 11, 1 12, 2.5 12 C 4.5 12, 6 13.5, 7.5 16 C 9 18.5, 11.5 20, 14.5 20 C 19.5 20, 23.5 15.5, 23.5 10 C 23.5 4.5, 19.5 1, 14.5 1 C 11.5 1, 9 2.5, 7.5 4.5 L 9.8 6.2 C 11 4.8, 12.5 4, 14.5 4 Z" fill="#2dd4bf" />
  </g>

  <!-- Header Title -->
  <text x="56" y="26" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="15" font-weight="600">Contributions</text>

  <!-- ==================== LINE CHART ==================== -->
  <!-- Y-Axis Title -->
  <text transform="rotate(-90)" x="-{chart_y_top + chart_height / 2:.1f}" y="42" text-anchor="middle" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="11" font-weight="600">Contributions</text>

  <!-- Y-Axis Ticks & Gridlines -->
  {''.join(y_axis_elements)}

  <!-- Vertical Gridlines for Days -->
  {''.join(vertical_grid_lines)}

  <!-- Baseline -->
  <line x1="{chart_x_start}" y1="{chart_y_base}" x2="{chart_x_end}" y2="{chart_y_base}" stroke="#21262d" stroke-width="1"/>

  <!-- Gradient Area Under Curve -->
  <path d="{area_str}" fill="url(#area-gradient)" />

  <!-- Blue Line Plot -->
  <path d="{line_str}" stroke="#388bfd" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>

  <!-- Blue Dots -->
  {''.join(blue_dots)}

  <!-- X-Axis Day Numbers -->
  {''.join(x_labels)}

  <!-- X-Axis "Days" Title -->
  <text x="{(chart_x_start + chart_x_end) / 2:.1f}" y="284" text-anchor="middle" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="11" font-weight="600">Days</text>

  <!-- ==================== HEATMAP ==================== -->
  <g>
    {''.join(heatmap_rects)}
  </g>

  <!-- ==================== BOTTOM ACTIVITY BAR ==================== -->
  <g clip-path="url(#bar-clip)">
    <!-- Base background -->
    <rect x="{bar_x:.1f}" y="{bar_y}" width="{bar_w:.1f}" height="{bar_h}" fill="#01311f" />
    <!-- Activity segments -->
    {''.join(bar_segments)}
  </g>
</svg>"""
    return svg


def main():
    parser = argparse.ArgumentParser(description="Generate dynamic GitHub Contributions Graph SVG")
    parser.add_argument("--username", "-u", default=os.environ.get("GITHUB_ACTOR", "valaprashant97"),
                        help="GitHub username (default: valaprashant97)")
    parser.add_argument("--output", "-o", default="assets/contrib-chart.svg",
                        help="Output SVG file path (default: assets/contrib-chart.svg)")
    parser.add_argument("--token", "-t", default=None,
                        help="GitHub Access Token (optional, falls back to GITHUB_TOKEN or public scraping)")

    args = parser.parse_args()

    print(f"Generating contributions graph for @{args.username}...")
    days, total = get_contributions(args.username, args.token)

    if not days:
        print("Error: No contribution data retrieved.", file=sys.stderr)
        sys.exit(1)

    svg_content = generate_svg(days, total)

    # Validate generated SVG
    if not svg_content.startswith("<svg") or not svg_content.endswith("</svg>"):
        print("Error: Generated SVG failed integrity check.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(svg_content)

    print(f"Successfully generated {args.output} ({len(svg_content)} bytes, {total} total contributions).")


if __name__ == "__main__":
    main()
