# TeeVee Series Tracker

A lightweight web app prototype for tracking which movies or TV series have been downloaded and/or watched. The backend keeps a growing catalog of titles pulled from public sources and lets you maintain your personal library.

## Features

- Web-based dashboard to add entries, mark status, and track downloads/watched.
- Scheduled catalog refresh that scrapes public sources (Wikipedia today) and keeps the catalog growing across recent years.
- API endpoints ready for a multi-user web app.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

## Catalog refresh

- The scheduler refreshes the catalog every 12 hours, re-scraping configured sources and adding newly discovered titles.
- Use the **Refresh catalog** button for an immediate update.
- `app/scraper.py` is the place to add more sources (IMDb, TheMovieDB, etc.). Use `CATALOG_MIN_YEAR` to control how far back the Wikipedia ingestion runs.

## Notes on scraping

Some sources require API keys or have stricter robots rules. Start with public lists (like Wikipedia) and add compliant sources with proper caching and rate limits.
