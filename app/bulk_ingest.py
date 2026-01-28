import argparse
import csv
import gzip
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Iterator

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Base, CatalogTitle, Episode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class TitleRecord:
    tconst: str
    title_type: str
    primary_title: str
    start_year: int | None
    end_year: int | None


@dataclass
class RatingRecord:
    tconst: str
    rating: float | None


@dataclass
class EpisodeRecord:
    tconst: str
    parent_tconst: str
    season_number: int | None
    episode_number: int | None


@dataclass
class EpisodeTitleRecord:
    tconst: str
    title: str
    start_year: int | None


def open_tsv(path: str) -> Iterator[dict[str, str]]:
    with gzip.open(path, mode="rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            yield row


def parse_int(value: str) -> int | None:
    if not value or value == "\\N":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_float(value: str) -> float | None:
    if not value or value == "\\N":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_title_basics(path: str, limit: int | None = None) -> Iterable[TitleRecord]:
    count = 0
    for row in open_tsv(path):
        if limit and count >= limit:
            break
        title_type = row.get("titleType", "")
        if title_type not in {"movie", "tvSeries", "tvMiniSeries"}:
            continue
        yield TitleRecord(
            tconst=row.get("tconst", ""),
            title_type=title_type,
            primary_title=row.get("primaryTitle", ""),
            start_year=parse_int(row.get("startYear", "")),
            end_year=parse_int(row.get("endYear", "")),
        )
        count += 1


def load_title_ratings(path: str, limit: int | None = None) -> Iterable[RatingRecord]:
    count = 0
    for row in open_tsv(path):
        if limit and count >= limit:
            break
        yield RatingRecord(
            tconst=row.get("tconst", ""),
            rating=parse_float(row.get("averageRating", "")),
        )
        count += 1


def load_episode_map(path: str, limit: int | None = None) -> Iterable[EpisodeRecord]:
    count = 0
    for row in open_tsv(path):
        if limit and count >= limit:
            break
        yield EpisodeRecord(
            tconst=row.get("tconst", ""),
            parent_tconst=row.get("parentTconst", ""),
            season_number=parse_int(row.get("seasonNumber", "")),
            episode_number=parse_int(row.get("episodeNumber", "")),
        )
        count += 1


def load_episode_titles(path: str, limit: int | None = None) -> Iterable[EpisodeTitleRecord]:
    count = 0
    for row in open_tsv(path):
        if limit and count >= limit:
            break
        title_type = row.get("titleType", "")
        if title_type != "tvEpisode":
            continue
        yield EpisodeTitleRecord(
            tconst=row.get("tconst", ""),
            title=row.get("primaryTitle", ""),
            start_year=parse_int(row.get("startYear", "")),
        )
        count += 1


def imdb_title_type_to_media(title_type: str) -> str:
    return "series" if title_type in {"tvSeries", "tvMiniSeries"} else "movie"


def upsert_imdb_titles(
    session, titles: Iterable[TitleRecord], rating_map: dict[str, float | None]
) -> tuple[int, int]:
    created = 0
    updated = 0
    for record in titles:
        if not record.tconst or not record.primary_title:
            continue
        existing = (
            session.execute(
                select(CatalogTitle)
                .where(
                    CatalogTitle.external_id == record.tconst,
                    CatalogTitle.source == "imdb",
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        rating = rating_map.get(record.tconst)
        if existing:
            changed = False
            if record.start_year and not existing.year:
                existing.year = record.start_year
                changed = True
            if rating is not None and existing.rating is None:
                existing.rating = rating
                changed = True
            if changed:
                updated += 1
            continue
        session.add(
            CatalogTitle(
                title=record.primary_title,
                media_type=imdb_title_type_to_media(record.title_type),
                year=record.start_year,
                source="imdb",
                source_url=f"https://www.imdb.com/title/{record.tconst}/",
                external_id=record.tconst,
                rating=rating,
            )
        )
        created += 1
    session.commit()
    return created, updated


def build_catalog_lookup(session) -> dict[str, int]:
    results = session.execute(
        select(CatalogTitle.id, CatalogTitle.external_id).where(
            CatalogTitle.source == "imdb", CatalogTitle.external_id.isnot(None)
        )
    ).all()
    return {external_id: catalog_id for catalog_id, external_id in results if external_id}


def upsert_imdb_episodes(
    session,
    catalog_lookup: dict[str, int],
    episode_map: Iterable[EpisodeRecord],
    episode_titles: dict[str, EpisodeTitleRecord],
) -> tuple[int, int]:
    created = 0
    updated = 0
    for episode in episode_map:
        if not episode.tconst or not episode.parent_tconst:
            continue
        catalog_id = catalog_lookup.get(episode.parent_tconst)
        if not catalog_id:
            continue
        title_record = episode_titles.get(episode.tconst)
        if not title_record:
            continue
        existing = (
            session.execute(
                select(Episode)
                .where(
                    Episode.catalog_id == catalog_id,
                    Episode.season_number == episode.season_number,
                    Episode.episode_number == episode.episode_number,
                    Episode.title == title_record.title,
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing:
            changed = False
            if title_record.start_year and not existing.air_date:
                existing.air_date = str(title_record.start_year)
                changed = True
            if changed:
                updated += 1
            continue
        session.add(
            Episode(
                catalog_id=catalog_id,
                title=title_record.title,
                season_number=episode.season_number,
                episode_number=episode.episode_number,
                air_date=str(title_record.start_year) if title_record.start_year else None,
                description=None,
                source="imdb",
                source_url=f"https://www.imdb.com/title/{episode.tconst}/",
            )
        )
        created += 1
    session.commit()
    return created, updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk ingest IMDb TSV datasets into the catalog database."
    )
    parser.add_argument("--basics", required=True, help="Path to title.basics.tsv.gz")
    parser.add_argument("--ratings", required=True, help="Path to title.ratings.tsv.gz")
    parser.add_argument("--episodes", required=True, help="Path to title.episode.tsv.gz")
    parser.add_argument("--episode-titles", required=True, help="Path to title.basics.tsv.gz")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        logger.info("Loading ratings from %s", args.ratings)
        rating_map = {
            record.tconst: record.rating
            for record in load_title_ratings(args.ratings, args.limit)
        }
        logger.info("Loading title basics from %s", args.basics)
        titles = load_title_basics(args.basics, args.limit)
        added, updated = upsert_imdb_titles(db, titles, rating_map)
        logger.info("Catalog ingest done. Added %s, updated %s.", added, updated)

        logger.info("Building catalog lookup for episodes")
        catalog_lookup = build_catalog_lookup(db)

        logger.info("Loading episode map from %s", args.episodes)
        episode_map = load_episode_map(args.episodes, args.limit)
        logger.info("Loading episode titles from %s", args.episode_titles)
        episode_title_map = {
            record.tconst: record
            for record in load_episode_titles(args.episode_titles, args.limit)
        }
        e_added, e_updated = upsert_imdb_episodes(
            db, catalog_lookup, episode_map, episode_title_map
        )
        logger.info("Episode ingest done. Added %s, updated %s.", e_added, e_updated)
    finally:
        db.close()


if __name__ == "__main__":
    main()
