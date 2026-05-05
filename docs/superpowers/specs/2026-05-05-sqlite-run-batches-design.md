# SQLite Run Batch Design

## Problem

Octopus currently uses two runtime data paths:

1. SQLite (`output/octopus.db`) for URL-based deduplication and historical article storage
2. `output/*_cache.json` files as the actual input contract for `scripts/summarize.py`

This split creates avoidable complexity:

- deduplication state and summary input are stored in different places
- successful empty runs must carefully overwrite cache files to avoid replaying stale data
- the daily pipeline cannot express "what belonged to this specific run" in SQLite
- future sources would need to keep following the JSON cache contract

The goal is to make SQLite the only runtime data source while preserving the current pipeline behavior: fetchers collect source data, summarize consumes only the current run's input set, and partial failures do not silently replay old data.

## Goals

- Make SQLite the only runtime input for `summarize.py`
- Preserve `articles` as the canonical historical deduplication table
- Add an explicit per-run model for "entries included in this run"
- Support partial source failures without reusing stale data
- Keep the design compatible with future `email` and `feishu` integration

## Non-Goals

- Reworking AI prompt logic in `summarize.py`
- Changing report markdown structure
- Enabling `email` or `feishu` immediately
- Preserving `*_cache.json` as part of the production runtime contract

## Recommended Architecture

Use a two-layer SQLite model:

1. **Historical layer:** `articles`
2. **Run layer:** `run_batches` and `batch_entries`

### Tables

#### `articles`

Keep the existing role unchanged:

- one canonical row per normalized URL / entry hash
- stores source metadata, summary, timestamps
- used for deduplication and long-term history

#### `run_batches`

Represents one execution of the pipeline.

Suggested columns:

- `run_id` TEXT PRIMARY KEY
- `run_date` TEXT NOT NULL — report date (`YYYY-MM-DD`)
- `status` TEXT NOT NULL — `running`, `completed`, `partial_failed`, `failed`
- `started_at` DATETIME NOT NULL
- `finished_at` DATETIME NULL
- `failed_sources` TEXT NOT NULL DEFAULT `[]` — JSON array of source names/types that failed

Purpose:

- gives every run an explicit identity
- lets downstream code query one specific execution
- makes partial failure visible instead of inferred from missing files

#### `batch_entries`

Associates the current run with the articles that should be summarized.

Suggested columns:

- `run_id` TEXT NOT NULL
- `entry_hash` TEXT NOT NULL
- `source_type` TEXT NOT NULL
- PRIMARY KEY (`run_id`, `entry_hash`)

Purpose:

- separates "article exists in history" from "article belongs to this run"
- lets `summarize.py` read exactly the current run's input set
- avoids replaying stale data on empty or failed runs

## Runtime Flow

### `scripts/run.sh`

`run.sh` becomes responsible for creating a run identity at the start of the pipeline.

Flow:

1. Compute `TODAY`
2. Create a `RUN_ID`
3. Export both to subprocesses, for example:
   - `OCTOPUS_DB`
   - `OCTOPUS_RUN_ID`
   - `OCTOPUS_RUN_DATE`
4. Initialize a `run_batches` row with status `running`
5. Execute fetchers
6. Execute `summarize.py` with `--run-id "$RUN_ID"`
7. Mark the batch `completed` or `partial_failed`

`run.sh` remains the orchestration boundary. It should not reconstruct input data itself.

### Fetchers (`fetch_rss.py`, `fetch_web.py`, `fetch_zhihu.py`)

For each fetched item:

1. Normalize / deduplicate against `articles`
2. Upsert or refresh the `articles` row
3. If the item should appear in the current daily report, attach it to `batch_entries` for the current `run_id`

This keeps the current source-specific extraction logic intact while moving "current run output" into SQLite.

### `scripts/summarize.py`

`summarize.py` should stop reading `*_cache.json` entirely.

Instead it should:

1. Accept a required `--run-id`
2. Query `batch_entries` joined with `articles`
3. Group entries by `source_type`
4. Generate commentary and markdown exactly as today

This preserves the summary output contract while removing runtime dependency on JSON cache files.

## Failure and Rerun Semantics

### Source failures

If one source fails:

- already-written `batch_entries` from successful sources remain valid
- the `run_batches.status` becomes `partial_failed`
- the failed source is recorded in `failed_sources`
- `summarize.py` still runs against the current run's successful entries

This matches the current intention in `run.sh`: Zhihu failure should not block the rest of the pipeline.

### Empty successful runs

If a run succeeds but produces zero new entries:

- `run_batches` is still recorded
- `batch_entries` is empty for that `run_id`
- `summarize.py` reads an empty set

This is the key behavior that removes stale-cache replay bugs.

### Full failures

If orchestration fails before any meaningful input is prepared:

- keep the batch row
- mark it `failed`
- do not borrow entries from prior runs

### Reruns

Every rerun creates a new `run_id`.

Do not overwrite or mutate an earlier batch to "reuse" it. A rerun is a new execution with its own result set. This keeps auditability and makes debugging easier.

## Migration Plan

### Phase 1: Database support

- add `run_batches` and `batch_entries` to `scripts/db.py`
- add helpers for:
  - creating a run batch
  - marking batch status
  - attaching entries to a batch
  - reading summarized input by `run_id`

### Phase 2: Summarize reads SQLite

- update `scripts/summarize.py` to require `--run-id`
- replace `load_cache()` usage with DB queries
- keep grouping and markdown generation behavior unchanged

### Phase 3: Active fetchers write batch associations

- update `fetch_rss.py`, `fetch_web.py`, and `fetch_zhihu.py`
- when a run id is present, write batch associations for this run

### Phase 4: Orchestration cutover

- update `scripts/run.sh` to create and pass `RUN_ID`
- finalize batch status after fetch and summarize steps

### Phase 5: Retire cache runtime path

- remove production reads of `*_cache.json`
- remove production writes of `rss_cache.json`, `web_cache.json`, and `zhihu_cache.json`
- later, when implemented, `email` and `feishu` should write directly into the same run-batch model rather than introducing new cache files

## Impact on `migrate.py`

`scripts/migrate.py` remains a historical import tool only.

It can continue reading legacy JSON cache files when backfilling old data into SQLite, but it is no longer part of the normal production pipeline contract. The normal runtime path becomes:

`fetchers -> SQLite -> summarize.py`

not:

`fetchers -> JSON cache -> summarize.py`

## Testing Strategy

Add or update tests for:

- schema creation for `run_batches` and `batch_entries`
- batch association writes from RSS/Web/Zhihu fetchers
- summarize loading entries by `run_id`
- empty successful runs producing empty summarize input
- partial failure semantics preserving successful-source entries
- `run.sh` exporting and passing a run id through the pipeline
- end-to-end regression showing no dependency on `*_cache.json`

## Alternatives Considered

### Infer current input from `articles.first_fetched`

Rejected because "first fetched today" is not the same as "belongs to this run". It breaks down on reruns, backfills, delayed runs, and partial retries.

### Keep dual support for SQLite and JSON cache

Rejected because it prolongs the split-brain runtime model and preserves unnecessary state synchronization risk.

### Source-specific pending tables

Rejected because it duplicates schema and logic per source instead of giving all sources one shared runtime contract.

## Open Decisions Resolved

These choices are fixed by this spec:

- SQLite becomes the sole runtime input source
- run membership is modeled explicitly with `run_id`
- JSON cache files are retired from production flow
- partial failures summarize only successful source entries from the same run
- reruns always create a new batch

