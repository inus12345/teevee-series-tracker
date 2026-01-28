from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogTitle, Episode
from app.scraper import CatalogItem, EpisodeItem


def is_valid_text(value: str | None, min_length: int = 2) -> bool:
    if not value:
        return False
    cleaned = value.strip()
    if len(cleaned) < min_length:
        return False
    if not any(char.isalnum() for char in cleaned):
        return False
    return True


def better_text(current: str | None, candidate: str | None) -> str | None:
    if not is_valid_text(candidate):
        return current
    if not is_valid_text(current):
        return candidate.strip()
    if len(candidate.strip()) > len(current.strip()):
        return candidate.strip()
    return current


def upsert_catalog_items(session: Session, items: Iterable[CatalogItem]) -> tuple[int, int]:
    created = 0
    updated = 0
    for item in items:
        if not is_valid_text(item.title):
            continue
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
            new_description = better_text(existing.description, item.description)
            if new_description != existing.description:
                existing.description = new_description
                changed = True
            new_release_date = better_text(existing.release_date, item.release_date)
            if new_release_date != existing.release_date:
                existing.release_date = new_release_date
                changed = True
            if item.rating is not None and (existing.rating is None or item.rating > existing.rating):
                existing.rating = item.rating
                changed = True
            if changed:
                updated += 1
            continue
        session.add(
            CatalogTitle(
                title=item.title.strip(),
                media_type=item.media_type,
                year=item.year,
                source=item.source,
                source_url=item.source_url,
                external_id=item.external_id,
                description=item.description.strip() if is_valid_text(item.description) else None,
                release_date=item.release_date.strip() if is_valid_text(item.release_date) else None,
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
        if not is_valid_text(item.title):
            continue
        if item.season_number is not None and item.episode_number is not None:
            existing = (
                session.execute(
                    select(Episode)
                    .where(
                        Episode.catalog_id == catalog_id,
                        Episode.season_number == item.season_number,
                        Episode.episode_number == item.episode_number,
                    )
                    .limit(1)
                )
                .scalars()
                .first()
            )
        else:
            existing = (
                session.execute(
                    select(Episode)
                    .where(
                        Episode.catalog_id == catalog_id,
                        Episode.title == item.title,
                    )
                    .limit(1)
                )
                .scalars()
                .first()
            )
        if existing:
            changed = False
            new_title = better_text(existing.title, item.title)
            if new_title != existing.title:
                existing.title = new_title
                changed = True
            new_air_date = better_text(existing.air_date, item.air_date)
            if new_air_date != existing.air_date:
                existing.air_date = new_air_date
                changed = True
            new_description = better_text(existing.description, item.description)
            if new_description != existing.description:
                existing.description = new_description
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
                title=item.title.strip(),
                season_number=item.season_number,
                episode_number=item.episode_number,
                air_date=item.air_date.strip() if is_valid_text(item.air_date) else None,
                description=item.description.strip() if is_valid_text(item.description) else None,
                source=item.source,
                source_url=item.source_url,
            )
        )
        created += 1
    session.commit()
    return created, updated
