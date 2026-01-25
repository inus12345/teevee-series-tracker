# TeeVee Series Tracker

A lightweight web app prototype for tracking which movies or TV series have been downloaded and/or watched. The backend keeps a growing catalog of titles pulled from public sources and lets you maintain your personal library.

## Features

- Web-based dashboard to add entries, mark status, and track downloads/watched.
- Scheduled catalog refresh that scrapes public sources (Wikipedia today) and keeps the catalog growing across recent years, including title metadata.
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

- The scheduler refreshes the catalog every 12 hours (override with `CATALOG_REFRESH_HOURS`), re-scraping configured sources and adding newly discovered titles plus metadata (description, release date, and ratings when available). Existing rows are updated when new metadata becomes available.
- Use the **Refresh catalog** button for an immediate update.
- `app/scraper.py` is the place to add more sources (IMDb, TheMovieDB, etc.). Use `CATALOG_MIN_YEAR` to control how far back the Wikipedia ingestion runs, `CATALOG_FETCH_SUMMARIES=false` if you want to disable per-title summary lookups, and `CATALOG_ENABLE_IMDB=false` to disable IMDb scraping.

### Dedicated refresh worker

If you want a standalone background worker (e.g., for a separate container or cron job), run:

```bash
python -m app.catalog_refresh --once
```

Or run it continuously on an interval:

```bash
python -m app.catalog_refresh --interval-hours 12
```

## Notes on scraping

Some sources require API keys or have stricter robots rules. Start with public lists (like Wikipedia) and add compliant sources with proper caching and rate limits.

## IMDb data

IMDb scraping is enabled by default via their suggestion API and title pages. Configure the queries with `CATALOG_IMDB_QUERIES` (comma-separated) and limit each query with `CATALOG_IMDB_LIMIT`. If you need to reduce scrape intensity, set `CATALOG_IMDB_DETAIL_DELAY_SECONDS` and `CATALOG_WIKI_SUMMARY_DELAY_SECONDS` to add per-item delays. To build a large, accurate catalog, plan to use licensed data sources (e.g., IMDb datasets, TMDB, or other APIs) and add ingestion jobs to `app/scraper.py`.
