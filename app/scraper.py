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


def fetch_wikipedia_titles(url: str, year: int, media_type: str) -> List[CatalogItem]:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.select("table.wikitable")
    items: List[CatalogItem] = []

    for table in tables[:2]:
        for row in table.select("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            title_cell = cells[0]
            title = title_cell.get_text(strip=True)
            if not title:
                continue
            items.append(
                CatalogItem(
                    title=title,
                    media_type=media_type,
                    year=year,
                    source="wikipedia",
                    source_url=url,
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
