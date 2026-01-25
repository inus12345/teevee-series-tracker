from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogTitle
from app.scraper import CatalogItem


def upsert_catalog_items(session: Session, items: Iterable[CatalogItem]) -> int:
    created = 0
    for item in items:
        existing = session.execute(
            select(CatalogTitle).where(
                CatalogTitle.title == item.title,
                CatalogTitle.source == item.source,
                CatalogTitle.media_type == item.media_type,
            )
        ).scalar_one_or_none()
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
            )
        )
        created += 1
    session.commit()
    return created
