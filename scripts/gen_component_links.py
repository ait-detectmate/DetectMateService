"""Regenerate the library component tables in ``docs/configuration.md``.

The tables list every parser and detector DetectMateLibrary documents.

Not maintained by hand: the entries are whatever the library documentation lists
under its parsers and detectors sections, read from its sitemap.xml, and each one has
the name of the headline of the respective page.

Usage::

    uv run python scripts/gen_component_links.py            # rewrite the tables
    uv run python scripts/gen_component_links.py --check    # exit 1 if they are out of date
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

import requests
# always against latest library docs
BASE_URL = "https://ait-detectmate.github.io/DetectMateLibrary/latest"
# the service docs file this script edits
DOCS_FILE = Path(__file__).resolve().parent.parent / "docs" / "configuration.md"
TIMEOUT = 20
SECTIONS = ("parsers", "detectors")


def fetch_sitemap() -> str:
    """Download the library documentation's sitemap."""
    response = requests.get(f"{BASE_URL}/sitemap.xml", timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def page_names(sitemap: str, section: str) -> list[str]:
    """e.g. ``new_value``"""
    # <section>/<page> part of a location is used
    pattern = re.compile(rf"/{section}/([^/]+)/?$")
    names = {match.group(1) for location in re.findall(r"<loc>([^<]+)</loc>", sitemap)
             if (match := pattern.search(location))}
    return sorted(names)


def page_title(url: str, page: str) -> str:
    """Read a page's headline, e.g. ``New Value Detector``.

    Falls back to the page name if the page cannot be read or there is
    no headline.
    """
    try:
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"warning: cannot read {url}: {exc}", file=sys.stderr)
        return page

    heading = re.search(r"<h1[^>]*>([^<]*)</h1>", response.text)
    if heading is None:
        print(f"warning: {url} has no headline", file=sys.stderr)
        return page
    return heading.group(1).strip() or page


def render_table(pages: Sequence[str], section: str) -> str:
    """Render one markdown table with links to each component's docs page."""
    rows = []
    for page in pages:
        url = f"{BASE_URL}/{section}/{page}/"
        rows.append(f"| [{page_title(url, page)}]({url}) |")

    lines = [f"| {section.rstrip('s').title()} |", "|---|"]
    return "\n".join(lines + sorted(rows, key=str.lower)) + "\n"


def replace_block(text: str, marker: str, content: str) -> str:
    """Replace everything between the <!-- Start x --> / <!-- End x -->
    markers."""
    start, end = f"<!-- Start {marker} -->", f"<!-- End {marker} -->"
    if start not in text or end not in text or text.index(start) > text.index(end):
        raise SystemExit(f"'{start}' is missing or comes after '{end}'")
    return f"{text[: text.index(start) + len(start)]}\n{content}{text[text.index(end):]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only report whether the tables changed")
    check = parser.parse_args().check

    try:
        sitemap = fetch_sitemap()
    except requests.RequestException as exc:
        print(f"error: cannot read the library documentation: {exc}", file=sys.stderr)
        return 1

    text = original = DOCS_FILE.read_text()
    for section in SECTIONS:
        names = page_names(sitemap, section)
        if not names:
            print(f"error: no {section} pages found under {BASE_URL}", file=sys.stderr)
            return 1
        text = replace_block(text, section, render_table(names, section))

    if text == original:
        print(f"{DOCS_FILE}: up to date")
        return 0
    if check:
        print(f"error: {DOCS_FILE} is out of date, run scripts/gen_component_links.py",
              file=sys.stderr)
        return 1

    DOCS_FILE.write_text(text)
    print(f"{DOCS_FILE}: updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
