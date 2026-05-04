# Octopus review fixes design

## Problem

The current codebase has three production-facing issues identified during code review:

1. `scripts/fetch_web.py` stores relative links directly as article URLs, which can produce broken links in output and false deduplication collisions across different sites.
2. `scripts/db.py` now defaults new timestamps to timezone-aware UTC values while the existing SQLite database already contains naive UTC timestamps, creating mixed formats in the same dataset.
3. `scripts/run.sh` loads `.env` with `export $(grep ... | xargs)`, which is unsafe for values containing spaces or shell-significant characters.

This work fixes those issues without changing pipeline scope, cache format, or the current SQLite schema.

## Goals

- Normalize website article links to absolute URLs before deduplication and output.
- Keep database timestamps consistent with the existing SQLite contents by using naive UTC defaults for now.
- Load `.env` in a shell-safe way that preserves values with spaces and special characters.
- Add regression tests that cover the repaired behavior.

## Non-goals

- No database migration to timezone-aware timestamps in this change.
- No refactor of the fetcher architecture or deduplication model.
- No changes to summary generation logic or daily output format.
- No cleanup of existing output artifacts or historical rows.

## Recommended approach

Use the smallest complete repair:

1. Update `scripts/fetch_web.py` to canonicalize extracted links with `urllib.parse.urljoin(base_url, href)`.
2. Change `scripts/db.py` timestamp defaults back to naive UTC values so old and new rows stay consistent.
3. Replace the `.env` loading line in `scripts/run.sh` with shell-native loading that exports assignments safely.
4. Extend tests around website deduplication and timestamp defaults, plus add coverage for the shell loading behavior if practical within the existing test layout.

This approach fixes the reported problems with the lowest operational risk and without introducing a migration dependency.

## Detailed design

### 1. Website URL normalization

`fetch_web()` will treat every extracted article link as an externalized URL:

- If an anchor is present, its `href` will be resolved against the page URL.
- If no anchor is present, the page URL remains the article URL.
- The normalized absolute URL becomes the single source of truth for:
  - database primary key lookup
  - inserted `Article.url`
  - cache JSON entry `url`
  - downstream Markdown links

This prevents collisions such as two unrelated sites both exposing `/article1`.

### 2. Timestamp consistency

The database model will keep using UTC semantics, but in the same naive format already present in `output/octopus.db`.

- `Article.first_fetched`
- `Article.last_seen`

Default values will be generated with naive UTC datetimes. No migration is required. This avoids mixed naive/aware values inside one repository database until a dedicated migration is designed.

### 3. `.env` loading

`scripts/run.sh` will stop using command substitution with `xargs`.

The replacement will:

- only run when `.env` exists
- export variables automatically while sourcing
- preserve spaces and special characters in values
- keep the rest of the script flow unchanged

This assumes `.env` remains valid shell assignment syntax, which already matches the repository’s documented usage.

## Testing plan

1. Add `fetch_web` coverage for relative-link normalization to absolute URLs.
2. Add `fetch_web` coverage proving two different base URLs with the same relative path do not deduplicate against each other.
3. Add `db` coverage asserting timestamp defaults are naive datetimes.
4. Run the existing repository checks:
   - `uv run ruff check scripts/`
   - `uv run pytest test/`
   - `uv run pyright scripts test`

## Risks and mitigations

- **Risk:** `.env` sourcing can execute shell syntax if the file contains arbitrary commands.  
  **Mitigation:** keep using the repository’s documented `.env` convention of plain assignments only; this change improves correctness for that existing contract rather than broadening it.

- **Risk:** URL normalization may alter test assumptions for relative paths.  
  **Mitigation:** update tests to assert the canonical absolute URLs explicitly.

- **Risk:** keeping naive UTC delays the long-term timezone cleanup.  
  **Mitigation:** this document intentionally defers that migration to a separate change so production data stays consistent now.

## Implementation outline

1. Modify `scripts/fetch_web.py` to normalize URLs before deduplication and output.
2. Modify `scripts/db.py` to restore naive UTC defaults.
3. Modify `scripts/run.sh` to safely source `.env`.
4. Update and extend the relevant tests.
5. Run lint, tests, and type checking.
