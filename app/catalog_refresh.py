import argparse
import time

from sqlalchemy import text

from app.db import SessionLocal, engine
from app.models import Base
from app.scraper import load_catalog_sources
from app.services import upsert_catalog_items


def refresh_once() -> tuple[int, int]:
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
        items = load_catalog_sources()
        return upsert_catalog_items(db, items)
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
        added, updated = refresh_once()
        print(f"Catalog refresh completed. Added {added} titles. Updated {updated}.")
        return

    interval_seconds = max(args.interval_hours, 0.25) * 3600
    while True:
        added, updated = refresh_once()
        print(f"Catalog refresh completed. Added {added} titles. Updated {updated}.")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
