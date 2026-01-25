from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogTitle, Episode
from app.scraper import CatalogItem, EpisodeItem


def upsert_catalog_items(session: Session, items: Iterable[CatalogItem]) -> tuple[int, int]:
    created = 0
    updated = 0
    for item in items:
        existing = (
            session.execute(
                select(CatalogTitle)
                .where(
                    CatalogTitle.title == item.title,
                    CatalogTitle.source == item.source,
                    CatalogTitle.media_type == item.media_type,
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing:
            changed = False
            if item.year and not existing.year:
                existing.year = item.year
                changed = True
            if item.source_url and not existing.source_url:
                existing.source_url = item.source_url
                changed = True
            if item.external_id and not existing.external_id:
                existing.external_id = item.external_id
                changed = True
            if item.description and not existing.description:
                existing.description = item.description
                changed = True
            if item.release_date and not existing.release_date:
                existing.release_date = item.release_date
                changed = True
            if item.rating is not None and existing.rating is None:
                existing.rating = item.rating
                changed = True
            if changed:
                updated += 1
            continue
        session.add(
            CatalogTitle(
                title=item.title,
                media_type=item.media_type,
                year=item.year,
                source=item.source,
                source_url=item.source_url,
                external_id=item.external_id,
                description=item.description,
                release_date=item.release_date,
                rating=item.rating,
            )
        )
        created += 1
    session.commit()
    return created, updated


def upsert_episode_items(
    session: Session, catalog_id: int, items: Iterable[EpisodeItem]
) -> tuple[int, int]:
    created = 0
    updated = 0
    for item in items:
        existing = (
            session.execute(
                select(Episode)
                .where(
                    Episode.catalog_id == catalog_id,
                    Episode.season_number == item.season_number,
                    Episode.episode_number == item.episode_number,
                    Episode.title == item.title,
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing:
            changed = False
            if item.air_date and not existing.air_date:
                existing.air_date = item.air_date
                changed = True
            if item.description and not existing.description:
                existing.description = item.description
                changed = True
            if item.source_url and not existing.source_url:
                existing.source_url = item.source_url
                changed = True
            if changed:
                updated += 1
            continue
        session.add(
            Episode(
                catalog_id=catalog_id,
                title=item.title,
                season_number=item.season_number,
                episode_number=item.episode_number,
                air_date=item.air_date,
                description=item.description,
                source=item.source,
                source_url=item.source_url,
            )
        )
        created += 1
    session.commit()
    return created, updated
