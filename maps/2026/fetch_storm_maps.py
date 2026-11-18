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
JMA_URL = "https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=jpn"
JMA_IMAGE_ROOT = "https://www.data.jma.go.jp/mscweb/data/himawari/img/jpn/"
VALID_BASINS = {"N", "E", "W", "I", "S", "P"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
CURRENT_DATA_RE = re.compile(
    r"Current Data\s*</th>.*?<th\b[^>]*colspan\s*=\s*['\"]?4['\"]?[^>]*>"
    r"\s*(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})\s+(\d{1,2}):(\d{2})\s+GMT",
    re.IGNORECASE | re.DOTALL,
)
JMA_TIME_OPTION_RE = re.compile(
    r"<option\b[^>]*value\s*=\s*['\"]?(\d{4})['\"]?[^>]*>"
    r"\s*(\d{1,2}:\d{2})\s+UTC\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
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
    return sorted(basins)


def parse_jma_snapshot(html: str) -> tuple[str, datetime]:
    match = JMA_TIME_OPTION_RE.search(html)
    if match is None:
        raise ValueError("Could not find the latest JMA Himawari image time.")

    slot, time_text, day, month, year = match.groups()
    parsed = datetime.strptime(
        f"{day} {month} {year} {time_text}", "%d %B %Y %H:%M"
    )
    return slot, parsed.replace(tzinfo=timezone.utc)


def himawari_product(image_time: datetime) -> tuple[str, str]:
    japan_hour = (image_time.hour + 9) % 24
    if 6 <= japan_hour < 18:
        return "trm", "True Color Reproduction"
    return "ngt", "Night Microphysics RGB"


def model_label(model_time: datetime) -> str:
    return (
        f"{model_time.day} {model_time.strftime('%b, %Y')} "
        f"{model_time.hour}:{model_time.minute:02d} GMT"
    )


def himawari_label(image_time: datetime) -> str:
    return (
        f"{image_time.day} {image_time.strftime('%b, %Y')} "
        f"{image_time.hour:02d}:{image_time.minute:02d} UTC"
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


def insert_himawari_entry(
    readme: str,
    image_time: datetime,
    image_name: str,
    product_label: str,
) -> str:
    section = "## Japanese Himawari RGB Satellite Images"
    heading = f"### {himawari_label(image_time)}"
    entry = f"{heading}\n\n{product_label}\n![{image_name}]({image_name})\n"

    if section not in readme:
        reference_heading = "## References"
        insertion_point = readme.find(reference_heading)
        if insertion_point < 0:
            insertion_point = len(readme)
        return (
            f"{readme[:insertion_point].rstrip()}\n\n"
            f"{section}\n\n{entry}\n"
            f"{readme[insertion_point:].lstrip()}"
        )

    section_start = readme.index(section) + len(section)
    section_end = readme.find("\n## ", section_start)
    if section_end < 0:
        section_end = len(readme)
    section_content = readme[section_start:section_end]

    if heading in section_content:
        if image_name in section_content:
            return readme
        heading_start = section_start + section_content.index(heading)
        next_heading = readme.find("\n### ", heading_start + len(heading))
        if next_heading < 0 or next_heading >= section_end:
            next_heading = section_end
        return (
            f"{readme[:next_heading].rstrip()}\n"
            f"{product_label}\n![{image_name}]({image_name})\n"
            f"{readme[next_heading:]}"
        )

    return (
        f"{readme[:section_start]}\n\n{entry}\n"
        f"{readme[section_start:].lstrip()}"
    )


def fetch_url(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "storm-map-archiver/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Failed to download {url}: {error}") from error


def fetch_bytes(url: str, signature: bytes, format_name: str) -> bytes:
    data = fetch_url(url)
    if not data.startswith(signature):
        raise RuntimeError(f"Downloaded content is not a {format_name}: {url}")
    return data


def fetch_text(url: str) -> str:
    return fetch_url(url).decode("utf-8")


def update_maps() -> list[str]:
    output_dir = Path(__file__).resolve().parent
    staging_dir = output_dir / "Images"
    readme_path = output_dir / "README.md"

    tracker_html = fetch_text(TRACKER_URL)
    jma_html = fetch_text(JMA_URL)
    model_time = parse_model_time(tracker_html)
    basins = parse_active_basins(tracker_html)
    jma_slot, jma_time = parse_jma_snapshot(jma_html)
    jma_product, jma_product_label = himawari_product(jma_time)

    prefix = model_time.strftime("%Y-%m-%d-%H%M")
    map_ids = ["globe", *basins]
    image_names = [f"{prefix}-{map_id}.png" for map_id in map_ids]
    jma_name = (
        f"{jma_time.strftime('%Y-%m-%d-%H%M')}-Himawari-Japan-{jma_product}.jpg"
    )

    readme = readme_path.read_text(encoding="utf-8")
    updated_readme = insert_readme_entry(readme, model_time, image_names)
    updated_readme = insert_himawari_entry(
        updated_readme, jma_time, jma_name, jma_product_label
    )

    staging_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_dir, prefix="download-") as temp_dir:
        temp_path = Path(temp_dir)
        for map_id, image_name in zip(map_ids, image_names, strict=True):
            image_url = f"{TRACKER_ROOT}images/{map_id}.png"
            (temp_path / image_name).write_bytes(
                fetch_bytes(image_url, PNG_SIGNATURE, "PNG")
            )

        jma_url = f"{JMA_IMAGE_ROOT}jpn_{jma_product}_{jma_slot}.jpg"
        (temp_path / jma_name).write_bytes(
            fetch_bytes(jma_url, JPEG_SIGNATURE, "JPEG")
        )

        for image_name in [*image_names, jma_name]:
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

    return [*image_names, jma_name]


def main() -> int:
    try:
        image_names = update_maps()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Storm map update failed: {error}", file=sys.stderr)
        return 1

    print(f"Updated TSR maps and Himawari imagery ({len(image_names)} images):")
    for image_name in image_names:
        print(f"  {image_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
