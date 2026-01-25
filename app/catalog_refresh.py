import argparse
import logging
import os
import time

from sqlalchemy import text

from app.db import SessionLocal, engine
from app.models import Base, CatalogTitle
from app.scraper import fetch_imdb_episodes, load_catalog_sources
from app.services import upsert_catalog_items, upsert_episode_items


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def refresh_once() -> tuple[int, int, int, int]:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        columns = {
            row[1]
            for row in db.execute(text("PRAGMA table_info(catalog_titles)")).fetchall()
        }
        if "description" not in columns:
            db.execute(text("ALTER TABLE catalog_titles ADD COLUMN description TEXT"))
        if "release_date" not in columns:
            db.execute(text("ALTER TABLE catalog_titles ADD COLUMN release_date TEXT"))
        if "rating" not in columns:
            db.execute(text("ALTER TABLE catalog_titles ADD COLUMN rating FLOAT"))
        db.commit()
        logger.info("Starting catalog scrape.")
        items = load_catalog_sources()
        added, updated = upsert_catalog_items(db, items)
        logger.info("Catalog scrape done. Added %s, updated %s.", added, updated)
        episodes_added = 0
        episodes_updated = 0
        if os.getenv("CATALOG_EPISODES_ENABLED", "true").lower() == "true":
            season = int(os.getenv("CATALOG_IMDB_EPISODE_SEASON", "1"))
            limit = int(os.getenv("CATALOG_IMDB_EPISODE_LIMIT", "25"))
            series = (
                db.query(CatalogTitle)
                .filter(
                    CatalogTitle.source == "imdb",
                    CatalogTitle.media_type == "series",
                    CatalogTitle.external_id.isnot(None),
                )
                .all()
            )
            logger.info("Starting episode scrape for %s series.", len(series))
            for entry in series:
                episodes = fetch_imdb_episodes(entry.external_id, season, limit)
                if not episodes:
                    continue
                add_count, update_count = upsert_episode_items(db, entry.id, episodes)
                episodes_added += add_count
                episodes_updated += update_count
            logger.info(
                "Episode scrape done. Added %s, updated %s.", episodes_added, episodes_updated
            )
        return added, updated, episodes_added, episodes_updated
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the catalog database from scraping sources."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single refresh and exit.",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=12.0,
        help="Loop refreshes every N hours when not running --once.",
    )
    args = parser.parse_args()

    if args.once:
        added, updated, episodes_added, episodes_updated = refresh_once()
        print(
            "Catalog refresh completed. "
            f"Added {added} titles. Updated {updated}. "
            f"Episodes added {episodes_added}. Episodes updated {episodes_updated}."
        )
        return

    interval_seconds = max(args.interval_hours, 0.25) * 3600
    while True:
        added, updated, episodes_added, episodes_updated = refresh_once()
        print(
            "Catalog refresh completed. "
            f"Added {added} titles. Updated {updated}. "
            f"Episodes added {episodes_added}. Episodes updated {episodes_updated}."
        )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
