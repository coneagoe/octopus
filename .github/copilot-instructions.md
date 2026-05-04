# Octopus Copilot Instructions

## Commands

```bash
# Lint (documented pre-commit command)
uv run ruff check scripts/

# Test suite
uv run pytest test/

# Single test
uv run pytest test/test_fetch_rss.py::TestFetchRssDedup::test_fetch_rss_returns_only_new_entries

# Type check (configured in pyproject.toml)
uv run pyright scripts test
```

## High-level architecture

- `scripts/run.sh` is the production entrypoint. Cron calls it, it loads `.env`, exports `OCTOPUS_DB` and `PYTHONPATH`, runs `fetch_rss.py`, `fetch_web.py`, `fetch_feishu.py`, and `fetch_email.py` in sequence, then calls `summarize.py` to write `output/daily/YYYY-MM-DD.md`, and finally commits `output/daily/` to Git.
- The pipeline uses two storage layers. RSS and web fetchers write newly discovered items into SQLite through `scripts/db.py` for URL-based deduplication (`Article` table), but the same run still passes data to `summarize.py` through `output/*_cache.json` files.
- `scripts/summarize.py` reads only the cache JSON files, not SQLite. It groups entries by source type and calls MiniMax once per item to generate the investment-style commentary that ends up in the daily Markdown note.
- `scripts/migrate.py` is a one-off bridge from the older JSON-cache-only workflow into the SQLite dedupe database. Use it when cache history needs to be backfilled into `output/octopus.db`.
- Feishu and email are part of the same pipeline contract even when they return no items: both scripts still emit cache files so summary generation can run without branching on missing inputs.

## Key conventions

- Keep imports rooted at `scripts.`. Runtime uses `PYTHONPATH="$REPO_DIR"` in `scripts/run.sh`, and tests mirror that by prepending the repo root to `sys.path` before importing `scripts.<module>`.
- Preserve the config schema in `scripts/config.yaml`: source definitions live under `sources.rss`, `sources.websites`, `sources.feishu`, and `sources.email`. Fetchers read that exact shape directly.
- Preserve the shared source-type vocabulary: `rss`, `web`, `feishu`, and `email`. Those strings are reused across cache entries, SQLite rows, and summary-section routing.
- When a fetcher needs a database path override, use the `OCTOPUS_DB` environment variable instead of hardcoding another path. Tests rely on that pattern with temporary SQLite files.
- Follow the repo’s test layout from `docs/coding_rule.md`: test files live in `test/test_<script>.py`, usually with one test class per script module.
- Prefer `pytest.MonkeyPatch` over `unittest.mock` when isolating dependencies. That is an explicit repository rule, not just a local style preference.
- User-facing log output and generated content are written in Chinese; keep that tone and wording consistent when changing CLI messages, config comments, or generated report text.
- `.env` and `logs/` are local-only artifacts. The automation intentionally commits `output/daily/` reports, so avoid changing that flow unless the task is specifically about publication behavior.

## Important environment details

- `summarize.py` exits if `MINIMAX_API_KEY` is missing.
- README documents `.env` entries for `GITHUB_PAT` and Feishu credentials, and `scripts/run.sh` is designed to load them automatically before running the pipeline.
