from contextlib import asynccontextmanager
from typing import List

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Base, CatalogTitle, LibraryEntry
from app.schemas import (
    CatalogTitleResponse,
    LibraryEntryCreate,
    LibraryEntryResponse,
    LibraryEntryUpdate,
)
from app.scraper import load_catalog_sources
from app.services import upsert_catalog_items

scheduler = BackgroundScheduler()


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


def refresh_catalog(db: Session) -> int:
    items = load_catalog_sources()
    return upsert_catalog_items(db, items)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_catalog_schema(db)
    finally:
        db.close()
    scheduler.add_job(
        lambda: refresh_catalog(SessionLocal()),
        "interval",
        hours=12,
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
    created = refresh_catalog(db)
    return {"added": created}


@app.get("/api/library", response_model=List[LibraryEntryResponse])
def list_library(db: Session = Depends(get_db)):
    entries = db.execute(select(LibraryEntry).order_by(LibraryEntry.created_at)).scalars().all()
    return entries


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
