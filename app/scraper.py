from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Iterable, List

import requests
from bs4 import BeautifulSoup

USER_AGENT = "TeeVeeTracker/1.0 (+https://example.com)"


@dataclass
class CatalogItem:
    title: str
    media_type: str
    year: int | None
    source: str
    source_url: str
    external_id: str | None = None
    description: str | None = None
    release_date: str | None = None
    rating: float | None = None


def normalize_header(text: str) -> str:
    return " ".join(text.lower().split())


def fetch_wikipedia_summary(title_slug: str) -> str | None:
    if not title_slug:
        return None
    api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title_slug}"
    try:
        response = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None
    data = response.json()
    return data.get("extract")


def extract_release_date(headers: List[str], cells: List[str]) -> str | None:
    for idx, header in enumerate(headers):
        if "release date" in header or "first aired" in header or "release" in header:
            if idx < len(cells):
                return cells[idx]
    return None


def extract_rating(headers: List[str], cells: List[str]) -> float | None:
    for idx, header in enumerate(headers):
        if "rating" in header:
            if idx < len(cells):
                text = cells[idx]
                digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
                try:
                    return float(digits)
                except ValueError:
                    return None
    return None


def extract_description(headers: List[str], cells: List[str]) -> str | None:
    for idx, header in enumerate(headers):
        if "notes" in header or "description" in header:
            if idx < len(cells):
                return cells[idx]
    return None


def fetch_wikipedia_titles(url: str, year: int, media_type: str) -> List[CatalogItem]:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.select("table.wikitable")
    items: List[CatalogItem] = []

    fetch_summaries = os.getenv("CATALOG_FETCH_SUMMARIES", "true").lower() == "true"

    for table in tables[:2]:
        header_cells = table.select("tr th")
        headers = [normalize_header(cell.get_text(" ", strip=True)) for cell in header_cells]
        for row in table.select("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            title_cell = cells[0]
            title = title_cell.get_text(strip=True)
            if not title:
                continue
            cell_text = [cell.get_text(" ", strip=True) for cell in cells]
            description = extract_description(headers, cell_text)
            release_date = extract_release_date(headers, cell_text)
            rating = extract_rating(headers, cell_text)
            summary = None
            if fetch_summaries:
                link = title_cell.find("a")
                if link and link.get("href", "").startswith("/wiki/"):
                    title_slug = link["href"].split("/wiki/")[-1]
                    summary = fetch_wikipedia_summary(title_slug)
            items.append(
                CatalogItem(
                    title=title,
                    media_type=media_type,
                    year=year,
                    source="wikipedia",
                    source_url=url,
                    description=summary or description,
                    release_date=release_date,
                    rating=rating,
                )
            )
    return items


def fetch_imdb_placeholder() -> List[CatalogItem]:
    return []


def wikipedia_sources(min_year: int, max_year: int) -> Iterable[tuple[str, int, str]]:
    for year in range(max_year, min_year - 1, -1):
        yield (
            f"https://en.wikipedia.org/wiki/List_of_American_films_of_{year}",
            year,
            "movie",
        )
        yield (
            f"https://en.wikipedia.org/wiki/List_of_American_television_series_of_{year}",
            year,
            "series",
        )


def load_catalog_sources() -> Iterable[CatalogItem]:
    current_year = datetime.utcnow().year
    min_year = int(os.getenv("CATALOG_MIN_YEAR", current_year - 1))
    for url, year, media_type in wikipedia_sources(min_year, current_year):
        yield from fetch_wikipedia_titles(url, year, media_type)

    yield from fetch_imdb_placeholder()
