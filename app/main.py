from contextlib import asynccontextmanager
import os
from typing import List

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Base, CatalogTitle, Episode, LibraryEntry
from app.schemas import (
    CatalogTitleResponse,
    EpisodeResponse,
    LibraryEntryCreate,
    LibraryEntryResponse,
    LibraryEntryUpdate,
)
from app.scraper import fetch_imdb_episodes, load_catalog_sources
from app.services import upsert_catalog_items, upsert_episode_items

scheduler = BackgroundScheduler()
REFRESH_INTERVAL_HOURS = float(os.getenv("CATALOG_REFRESH_HOURS", "12"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_catalog_schema(db: Session) -> None:
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


def refresh_catalog(db: Session) -> tuple[int, int]:
    items = load_catalog_sources()
    return upsert_catalog_items(db, items)


def refresh_series_episodes(db: Session) -> tuple[int, int]:
    if os.getenv("CATALOG_EPISODES_ENABLED", "true").lower() != "true":
        return 0, 0
    season = int(os.getenv("CATALOG_IMDB_EPISODE_SEASON", "1"))
    limit = int(os.getenv("CATALOG_IMDB_EPISODE_LIMIT", "25"))
    created = 0
    updated = 0
    series = (
        db.execute(
            select(CatalogTitle)
            .where(
                CatalogTitle.source == "imdb",
                CatalogTitle.media_type == "series",
                CatalogTitle.external_id.isnot(None),
            )
            .order_by(CatalogTitle.id)
        )
        .scalars()
        .all()
    )
    for entry in series:
        episodes = fetch_imdb_episodes(entry.external_id, season, limit)
        if not episodes:
            continue
        add_count, update_count = upsert_episode_items(db, entry.id, episodes)
        created += add_count
        updated += update_count
    return created, updated


def run_scheduled_refresh() -> None:
    db = SessionLocal()
    try:
        refresh_catalog(db)
        refresh_series_episodes(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_catalog_schema(db)
    finally:
        db.close()
    scheduler.add_job(
        run_scheduled_refresh,
        "interval",
        hours=REFRESH_INTERVAL_HOURS,
        id="catalog_refresh",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/catalog", response_model=List[CatalogTitleResponse])
def list_catalog(db: Session = Depends(get_db)):
    titles = db.execute(select(CatalogTitle).order_by(CatalogTitle.title)).scalars().all()
    return titles


@app.get("/api/catalog/search", response_model=List[CatalogTitleResponse])
def search_catalog(q: str, db: Session = Depends(get_db)):
    query = q.strip()
    if not query:
        return []
    titles = (
        db.execute(
            select(CatalogTitle)
            .where(CatalogTitle.title.ilike(f"%{query}%"))
            .order_by(CatalogTitle.title)
            .limit(8)
        )
        .scalars()
        .all()
    )
    return titles


@app.post("/api/catalog/refresh")
def refresh_catalog_endpoint(db: Session = Depends(get_db)):
    added, updated = upsert_catalog_items(db, load_catalog_sources())
    episodes_added, episodes_updated = refresh_series_episodes(db)
    return {
        "added": added,
        "updated": updated,
        "episodes_added": episodes_added,
        "episodes_updated": episodes_updated,
    }


@app.get("/api/library", response_model=List[LibraryEntryResponse])
def list_library(db: Session = Depends(get_db)):
    entries = db.execute(select(LibraryEntry).order_by(LibraryEntry.created_at)).scalars().all()
    return entries


@app.get("/api/catalog/{catalog_id}/episodes", response_model=List[EpisodeResponse])
def list_episodes(catalog_id: int, db: Session = Depends(get_db)):
    episodes = (
        db.execute(select(Episode).where(Episode.catalog_id == catalog_id))
        .scalars()
        .all()
    )
    return episodes


@app.post("/api/library", response_model=LibraryEntryResponse)
def create_library_entry(payload: LibraryEntryCreate, db: Session = Depends(get_db)):
    entry = LibraryEntry(**payload.dict())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.patch("/api/library/{entry_id}", response_model=LibraryEntryResponse)
def update_library_entry(
    entry_id: int, payload: LibraryEntryUpdate, db: Session = Depends(get_db)
):
    entry = db.get(LibraryEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(entry, key, value)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.delete("/api/library/{entry_id}")
def delete_library_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(LibraryEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}
