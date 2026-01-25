from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogTitle
from app.scraper import CatalogItem


def upsert_catalog_items(session: Session, items: Iterable[CatalogItem]) -> int:
    created = 0
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
    return created
