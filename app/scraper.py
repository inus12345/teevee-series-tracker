from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
import time
from typing import Iterable, List

import requests
from bs4 import BeautifulSoup

USER_AGENT = "TeeVeeTracker/1.0 (+https://example.com)"
IMDB_SUGGEST_URL = "https://v2.sg.media-imdb.com/suggestion"
IMDB_TITLE_URL = "https://www.imdb.com/title"
TMDB_API_URL = "https://api.themoviedb.org/3"
TVMAZE_API_URL = "https://api.tvmaze.com"
OMDB_API_URL = "https://www.omdbapi.com"

logger = logging.getLogger(__name__)


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


@dataclass
class EpisodeItem:
    title: str
    season_number: int | None
    episode_number: int | None
    air_date: str | None
    description: str | None
    source: str
    source_url: str


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
    summary_delay = float(os.getenv("CATALOG_WIKI_SUMMARY_DELAY_SECONDS", "0"))

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
                    if summary_delay > 0:
                        time.sleep(summary_delay)
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
    queries = [
        query.strip()
        for query in os.getenv("CATALOG_IMDB_QUERIES", "star,night").split(",")
        if query.strip()
    ]
    if not queries:
        return []
    limit = int(os.getenv("CATALOG_IMDB_LIMIT", "20"))
    items: List[CatalogItem] = []
    for query in queries:
        items.extend(fetch_imdb_suggestions(query, limit))
    return items


def imdb_suggestion_url(query: str) -> str:
    slug = query[0].lower()
    return f"{IMDB_SUGGEST_URL}/{slug}/{query}.json"


def imdb_title_type_to_media(title_type: str | None) -> str:
    if not title_type:
        return "movie"
    title_type = title_type.lower()
    if "tv" in title_type or "series" in title_type:
        return "series"
    return "movie"


def fetch_imdb_suggestions(query: str, limit: int) -> List[CatalogItem]:
    try:
        response = requests.get(
            imdb_suggestion_url(query), headers={"User-Agent": USER_AGENT}, timeout=20
        )
        response.raise_for_status()
    except requests.RequestException:
        return []
    data = response.json()
    results = data.get("d", [])[:limit]
    items: List[CatalogItem] = []
    detail_delay = float(os.getenv("CATALOG_IMDB_DETAIL_DELAY_SECONDS", "0"))
    for result in results:
        title_id = result.get("id")
        if not title_id:
            continue
        title_url = f"{IMDB_TITLE_URL}/{title_id}/"
        details = fetch_imdb_title_details(title_url)
        if detail_delay > 0:
            time.sleep(detail_delay)
        items.append(
            CatalogItem(
                title=result.get("l", ""),
                media_type=imdb_title_type_to_media(result.get("q")),
                year=result.get("y"),
                source="imdb",
                source_url=title_url,
                external_id=title_id,
                description=details.get("description"),
                release_date=details.get("release_date"),
                rating=details.get("rating"),
            )
        )
    return items


def fetch_imdb_episodes(title_id: str, season: int, limit: int) -> List[EpisodeItem]:
    url = f"{IMDB_TITLE_URL}/{title_id}/episodes?season={season}"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    data: dict | None = None
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") == "TVSeason":
            data = payload
            break
    if not data:
        return []
    items: List[EpisodeItem] = []
    for entry in data.get("episode", [])[:limit]:
        if not isinstance(entry, dict):
            continue
        items.append(
            EpisodeItem(
                title=entry.get("name", ""),
                season_number=season,
                episode_number=entry.get("episodeNumber"),
                air_date=entry.get("datePublished"),
                description=entry.get("description"),
                source="imdb",
                source_url=entry.get("url", url),
            )
        )
    return items


def fetch_imdb_title_details(url: str) -> dict:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return {}
    soup = BeautifulSoup(response.text, "html.parser")
    data = {}
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") in {"Movie", "TVSeries"}:
            data["description"] = payload.get("description")
            data["release_date"] = payload.get("datePublished")
            rating = payload.get("aggregateRating", {}).get("ratingValue")
            if rating is not None:
                try:
                    data["rating"] = float(rating)
                except (TypeError, ValueError):
                    data["rating"] = None
            break
    return data


def fetch_tmdb_titles() -> List[CatalogItem]:
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return []
    page_limit = int(os.getenv("TMDB_PAGE_LIMIT", "2"))
    page_delay = float(os.getenv("CATALOG_PAGE_DELAY_SECONDS", "0"))
    items: List[CatalogItem] = []
    for page in range(1, page_limit + 1):
        for endpoint, media_type in (("discover/movie", "movie"), ("discover/tv", "series")):
            try:
                response = requests.get(
                    f"{TMDB_API_URL}/{endpoint}",
                    params={"api_key": api_key, "page": page},
                    headers={"User-Agent": USER_AGENT},
                    timeout=20,
                )
                response.raise_for_status()
            except requests.RequestException:
                continue
            data = response.json()
            for entry in data.get("results", []):
                title = entry.get("title") or entry.get("name")
                if not title:
                    continue
                release_date = entry.get("release_date") or entry.get("first_air_date")
                year = parse_year(release_date)
                items.append(
                    CatalogItem(
                        title=title,
                        media_type=media_type,
                        year=year,
                        source="tmdb",
                        source_url=f"https://www.themoviedb.org/{'movie' if media_type == 'movie' else 'tv'}/{entry.get('id')}",
                        external_id=str(entry.get("id")) if entry.get("id") else None,
                        description=entry.get("overview"),
                        release_date=release_date,
                        rating=entry.get("vote_average"),
                    )
                )
            if page_delay > 0:
                time.sleep(page_delay)
    return items


def fetch_tvmaze_titles() -> List[CatalogItem]:
    if os.getenv("TVMAZE_ENABLED", "true").lower() != "true":
        return []
    page_limit = int(os.getenv("TVMAZE_PAGE_LIMIT", "2"))
    page_delay = float(os.getenv("CATALOG_PAGE_DELAY_SECONDS", "0"))
    items: List[CatalogItem] = []
    for page in range(page_limit):
        try:
            response = requests.get(
                f"{TVMAZE_API_URL}/shows",
                params={"page": page},
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue
        data = response.json()
        for entry in data:
            title = entry.get("name")
            if not title:
                continue
            premiere = entry.get("premiered")
            items.append(
                CatalogItem(
                    title=title,
                    media_type="series",
                    year=parse_year(premiere),
                    source="tvmaze",
                    source_url=entry.get("url"),
                    external_id=str(entry.get("id")) if entry.get("id") else None,
                    description=strip_html(entry.get("summary")),
                    release_date=premiere,
                    rating=(entry.get("rating") or {}).get("average"),
                )
            )
        if page_delay > 0:
            time.sleep(page_delay)
    return items


def fetch_omdb_titles() -> List[CatalogItem]:
    api_key = os.getenv("OMDB_API_KEY")
    if not api_key:
        return []
    queries = [
        query.strip()
        for query in os.getenv("OMDB_QUERIES", "star,night").split(",")
        if query.strip()
    ]
    items: List[CatalogItem] = []
    page_limit = int(os.getenv("OMDB_PAGE_LIMIT", "2"))
    page_delay = float(os.getenv("CATALOG_PAGE_DELAY_SECONDS", "0"))
    for query in queries:
        for page in range(1, page_limit + 1):
            try:
                response = requests.get(
                    OMDB_API_URL,
                    params={"apikey": api_key, "s": query, "page": page},
                    headers={"User-Agent": USER_AGENT},
                    timeout=20,
                )
                response.raise_for_status()
            except requests.RequestException:
                continue
            data = response.json()
            for entry in data.get("Search", []):
                imdb_id = entry.get("imdbID")
                title = entry.get("Title")
                if not title:
                    continue
                items.append(
                    CatalogItem(
                        title=title,
                        media_type="series" if entry.get("Type") == "series" else "movie",
                        year=parse_year(entry.get("Year")),
                        source="omdb",
                        source_url=f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None,
                        external_id=imdb_id,
                        release_date=entry.get("Year"),
                    )
                )
            if page_delay > 0:
                time.sleep(page_delay)
    return items


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    for chunk in value.split("-"):
        chunk = chunk.strip()
        if chunk.isdigit():
            return int(chunk)
    return None


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


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


def wikipedia_collection_sources() -> Iterable[tuple[str, int | None, str]]:
    collections = [
        ("https://en.wikipedia.org/wiki/List_of_highest-grossing_films", None, "movie"),
        ("https://en.wikipedia.org/wiki/List_of_highest-grossing_films_in_the_United_States", None, "movie"),
        ("https://en.wikipedia.org/wiki/List_of_highest-grossing_animated_films", None, "movie"),
        ("https://en.wikipedia.org/wiki/List_of_highest-grossing_films_by_year", None, "movie"),
        ("https://en.wikipedia.org/wiki/List_of_animated_television_series", None, "series"),
        ("https://en.wikipedia.org/wiki/List_of_drama_television_series", None, "series"),
        ("https://en.wikipedia.org/wiki/List_of_comedy_television_series", None, "series"),
    ]
    for url, year, media_type in collections:
        yield url, year, media_type


def load_catalog_sources() -> Iterable[CatalogItem]:
    current_year = datetime.utcnow().year
    min_year = int(os.getenv("CATALOG_MIN_YEAR", current_year - 1))
    for url, year, media_type in wikipedia_sources(min_year, current_year):
        yield from fetch_wikipedia_titles(url, year, media_type)

    for url, year, media_type in wikipedia_collection_sources():
        yield from fetch_wikipedia_titles(url, year or current_year, media_type)

    if os.getenv("CATALOG_ENABLE_IMDB", "true").lower() == "true":
        yield from fetch_imdb_placeholder()

    yield from fetch_tmdb_titles()
    yield from fetch_tvmaze_titles()
    yield from fetch_omdb_titles()
