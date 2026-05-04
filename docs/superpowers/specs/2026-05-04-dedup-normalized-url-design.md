# Octopus dedup by normalized URL design

## Problem

The current deduplication behavior in Octopus uses the raw `url` as the article identity in SQLite. That is too weak for the actual duplicate pattern seen in RSS and website ingestion:

1. The same article URL can appear with different tracking parameters such as `utm_*`, `fbclid`, or `ref`.
2. The same page can be represented with equivalent but non-identical URL forms, such as host casing differences, default ports, or query parameter order.
3. The current pipeline goal is still narrow: an article should appear only on the first day it is fetched. This is a URL-level deduplication problem, not a cross-platform content-fingerprint problem.

The design therefore needs to make URL identity stable without expanding scope into content-level or syndication-level deduplication.

## Goals

- Deduplicate articles by a canonicalized URL identity instead of the raw input URL.
- Ensure the same normalized article is inserted only once and only appears in the first daily report.
- Keep the current pipeline shape intact: fetchers write cache JSON, and `summarize.py` consumes cache JSON.
- Make the deduplication rule explicit in schema, migration, and tests.
- Keep the solution deterministic and local-only, with no new network dependency in the deduplication path.

## Non-goals

- No cross-platform or repost-content deduplication in this change.
- No short-link expansion or redirect chasing during normalization.
- No use of `author`, `title`, or `published` as part of the primary deduplication key.
- No removal of existing `*_cache.json` files.
- No change to the high-level cron pipeline in `scripts/run.sh`.

## Approaches considered

### A. Deduplicate by `normalized_url` directly

Store both the original `url` and a canonical `normalized_url`, and enforce uniqueness on `normalized_url`.

**Pros**

- Matches the actual business goal: URL-level deduplication after noise removal.
- Easy to inspect and debug in SQLite.
- Keeps migration logic understandable.
- Avoids unstable dependencies on incomplete metadata such as author.

**Cons**

- Does not solve content-level repost detection.

### B. Deduplicate by `entry_hash(normalized_url)`

Compute a hash from the normalized URL and use that as the only stored identity.

**Pros**

- Compact storage and easy indexing.

**Cons**

- Worse operability because the real canonical URL is hidden behind a hash.
- Harder to debug migrations and collisions.
- Still represents only URL-level deduplication, so it does not add real semantic value over approach A.

### C. Deduplicate by `normalized_url + author`

Use normalized URL plus author-like metadata as the key.

**Pros**

- Can appear to distinguish reposts or republished items.

**Cons**

- Conflicts with the agreed goal of normalized URL deduplication.
- `author` is not stable or consistently available in current RSS and website fetchers.
- Risks splitting one canonical article into multiple rows for metadata reasons.

## Recommended approach

Use **approach A**.

The authoritative deduplication identity is `normalized_url`. The database stores:

- `url`: the original fetched URL for output and inspection
- `normalized_url`: the canonical URL used for uniqueness and deduplication

If an `entry_hash` field is kept, it is only a derived helper from `normalized_url`, not a separate semantic key.

`author` remains a normal field only. It is explicitly out of the primary uniqueness model in this design.

## URL normalization rules

`normalize_url(raw_url)` must be a pure local function with no network I/O.

It should:

1. Parse the URL and remove the fragment.
2. Lowercase the scheme and host.
3. Remove default ports such as `:80` for HTTP and `:443` for HTTPS.
4. Remove tracking query parameters, including:
   - explicit names such as `fbclid`, `ref`, `spm`, `scene`, `from`, `share`, `channel`
   - any parameter whose key starts with `utm_`
5. Sort the remaining query parameters by key and value so equivalent URLs normalize identically.
6. Preserve meaningful non-tracking query parameters.
7. Apply one explicit trailing-slash rule and test it. Recommended rule:
   - preserve `/path/` when it is part of the parsed path
   - do not add a trailing slash where one was not present

This keeps normalization conservative and predictable.

## Data model

### `articles`

Recommended model:

| Field | Purpose |
|---|---|
| `id` or `entry_hash` | Internal article key |
| `normalized_url` | Canonical deduplication key, unique |
| `url` | Original fetched URL |
| `author` | Optional metadata only |
| `title` | Article title |
| `source` | Source name |
| `source_type` | `rss` / `web` / `feishu` / `email` |
| `published` | Original published value if present |
| `summary` | Stored summary text |
| `first_fetched` | First time the canonical URL was seen |
| `last_seen` | Most recent time the canonical URL was seen |

Key constraints:

- `normalized_url` must have a unique constraint.
- `url` should not be the deduplication key.
- `author` should not participate in uniqueness.

### `daily_entries`

Recommended model change:

- Replace `(date, url)` with `(date, article_key)` or another stable reference to the article row.

This avoids keeping the reporting table tied to the non-canonical raw URL after the article model has moved to canonical URL identity.

## Data flow

### Fetch phase

`fetch_rss.py` and `fetch_web.py` should behave as the primary deduplication layer:

1. Extract the raw article URL.
2. Compute `normalized_url`.
3. Look up the article by `normalized_url`.
4. If found:
   - update `last_seen`
   - do not emit the item into the current cache
5. If not found:
   - insert the article row
   - set both `first_fetched` and `last_seen`
   - emit the item into the current cache

The cache files therefore remain the handoff contract to `summarize.py`, but now contain only newly discovered canonical articles.

### Summarize phase

`summarize.py` should continue reading only `*_cache.json`.

It may perform a lightweight in-memory defensive deduplication by `normalized_url` or article key if helpful, but it is not the primary deduplication authority. The source of truth remains the fetch plus database layer.

## Migration strategy

Existing rows currently keyed by raw `url` need a one-time migration to canonical URL identity.

Recommended migration behavior:

1. Add `normalized_url` to the article model.
2. Backfill `normalized_url = normalize_url(url)` for all historical rows.
3. When multiple historical rows normalize to the same canonical URL:
   - keep the earliest `first_fetched`
   - keep the latest `last_seen`
   - preserve one representative original `url`
   - merge or discard duplicate rows in a deterministic way
4. Add the unique constraint on `normalized_url` after backfill and conflict cleanup.
5. Update dependent tables such as `daily_entries` to reference the stable article identity rather than the raw URL.

The old cache JSON files remain as historical artifacts and backup material. They are not deleted by this design.

## Error handling

- URL normalization failures must be visible in logs.
- The code should not silently treat malformed input as successfully canonicalized.
- Database uniqueness must remain the final safeguard against duplicate insertion.
- No broad success-shaped fallback should hide canonicalization or migration issues.

Because normalization is pure and local, the deduplication path remains deterministic and does not depend on network reachability.

## Testing plan

Minimum required coverage:

1. URLs differing only by `utm_*`, `fbclid`, `ref`, or fragment normalize to one identity.
2. Query parameter order differences normalize to one identity.
3. Host casing and default-port differences normalize to one identity.
4. The chosen trailing-slash behavior is explicitly tested.
5. RSS and website fetchers both deduplicate against the same canonical URL.
6. Existing rows are migrated into canonical rows without creating duplicates.
7. `summarize.py` still generates output only from newly emitted cache entries.

Repository verification should continue using the existing commands:

- `uv run ruff check scripts/`
- `uv run pytest test/`
- `uv run pyright scripts test`

## Risks and mitigations

- **Risk:** Over-aggressive normalization can merge URLs that should remain distinct.  
  **Mitigation:** keep normalization conservative and explicitly test the chosen rules.

- **Risk:** Migration can collapse old rows unexpectedly when canonical URLs converge.  
  **Mitigation:** define deterministic merge rules before adding the unique constraint.

- **Risk:** Keeping both `url` and `normalized_url` introduces confusion if their roles are not clear.  
  **Mitigation:** document that `normalized_url` is the identity and `url` is the preserved source link.

## Out of scope for this design

- Cross-platform repost detection
- Content hashing or title-based clustering
- Redirect resolution for short links
- Using `author`, `title`, or `published` in the primary deduplication model
