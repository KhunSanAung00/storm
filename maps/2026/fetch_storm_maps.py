#!/usr/bin/env python3
"""Download the latest TSR tracker maps and add them to the 2026 event log."""

from __future__ import annotations

import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


TRACKER_URL = "https://www.tropicalstormrisk.com/tracker/dynamic/main.html"
TRACKER_ROOT = "https://www.tropicalstormrisk.com/tracker/dynamic/"
VALID_BASINS = {"N", "E", "W", "I", "S", "P"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CURRENT_DATA_RE = re.compile(
    r"Current Data\s*</th>.*?<th\b[^>]*colspan\s*=\s*['\"]?4['\"]?[^>]*>"
    r"\s*(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})\s+(\d{1,2}):(\d{2})\s+GMT",
    re.IGNORECASE | re.DOTALL,
)
ACTIVE_BASIN_RE = re.compile(
    r"<td\b[^>]*>\s*<a\b[^>]*href\s*=\s*['\"]?\.\/\d+[A-Z]\.html['\"]?[^>]*>"
    r".*?</a>\s*</td>\s*<td\b[^>]*>\s*<a\b[^>]*href\s*=\s*"
    r"['\"]?\.\/([A-Z])\.html['\"]?",
    re.IGNORECASE | re.DOTALL,
)


def parse_model_time(html: str) -> datetime:
    match = CURRENT_DATA_RE.search(html)
    if match is None:
        raise ValueError("Could not find the TSR Current Data model time.")

    day, month, year, hour, minute = match.groups()
    parsed = datetime.strptime(
        f"{day} {month} {year} {hour}:{minute}", "%d %b %Y %H:%M"
    )
    return parsed.replace(tzinfo=timezone.utc)


def parse_active_basins(html: str) -> list[str]:
    basins = {
        match.group(1).upper()
        for match in ACTIVE_BASIN_RE.finditer(html)
    }
    unknown_basins = basins - VALID_BASINS
    if unknown_basins:
        raise ValueError(
            "The TSR tracker contains unsupported basin codes: "
            + ", ".join(sorted(unknown_basins))
        )
    if not basins:
        raise ValueError("Could not find any active storm basin links.")
    return sorted(basins)


def model_label(model_time: datetime) -> str:
    return (
        f"{model_time.day} {model_time.strftime('%b, %Y')} "
        f"{model_time.hour}:{model_time.minute:02d} GMT"
    )


def insert_readme_entry(readme: str, model_time: datetime, image_names: list[str]) -> str:
    section = "## Global Current Active Storms"
    if section not in readme:
        raise ValueError(f"README is missing the expected heading: {section}")

    heading = f"### {model_label(model_time)}"
    if heading in readme:
        return readme

    images = " ".join(f"![{name}]({name})" for name in image_names)
    entry = f"{heading}\n\n{images}\n"
    section_end = readme.index(section) + len(section)
    return f"{readme[:section_end]}\n\n{entry}\n{readme[section_end:].lstrip()}"


def fetch_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "storm-map-archiver/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read()
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Failed to download {url}: {error}") from error

    if not data.startswith(PNG_SIGNATURE):
        raise RuntimeError(f"Downloaded content is not a PNG: {url}")
    return data


def update_maps() -> list[str]:
    output_dir = Path(__file__).resolve().parent
    staging_dir = output_dir / "Images"
    readme_path = output_dir / "README.md"

    html_request = Request(
        TRACKER_URL,
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "storm-map-archiver/1.0",
        },
    )
    try:
        with urlopen(html_request, timeout=30) as response:
            html = response.read().decode("utf-8")
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Failed to fetch the TSR tracker: {error}") from error

    model_time = parse_model_time(html)
    basins = parse_active_basins(html)
    prefix = model_time.strftime("%Y-%m-%d-%H%M")
    map_ids = ["globe", *basins]
    image_names = [f"{prefix}-{map_id}.png" for map_id in map_ids]

    readme = readme_path.read_text(encoding="utf-8")
    updated_readme = insert_readme_entry(readme, model_time, image_names)

    staging_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_dir, prefix="download-") as temp_dir:
        temp_path = Path(temp_dir)
        for map_id, image_name in zip(map_ids, image_names, strict=True):
            image_url = f"{TRACKER_ROOT}images/{map_id}.png"
            (temp_path / image_name).write_bytes(fetch_bytes(image_url))

        for image_name in image_names:
            (temp_path / image_name).replace(output_dir / image_name)

    if updated_readme != readme:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_dir,
            prefix="README-",
            suffix=".tmp",
            delete=False,
        ) as temp_readme:
            temp_readme.write(updated_readme)
            temp_readme_path = Path(temp_readme.name)
        temp_readme_path.replace(readme_path)

    return image_names


def main() -> int:
    try:
        image_names = update_maps()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Storm map update failed: {error}", file=sys.stderr)
        return 1

    print(f"Updated maps for the latest TSR model ({len(image_names)} images):")
    for image_name in image_names:
        print(f"  {image_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
