# ADAMS for Projects

A small Python CLI that queries the NRC **ADAMS Public Search (APS) API** for documents added **today** (or a specified date),
filters obvious noise, and surfaces the **Top N** “project-grade” items based on simple, transparent heuristics.

This is **not** an NRC project and is provided as-is.

## Quick start

### 1) Create a virtualenv & install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### 2) Set your APS key

Export your APS subscription key (Azure APIM key):

```bash
export APS_KEY="YOUR_KEY_HERE"
```

### 3) Run for today

```bash
adams --today --top 5
```

Or for a specific date:

```bash
adams --date 2026-02-28 --top 10
```

## Helpful modes

### Probe response schema (first time setup)
APS response field names can vary. This mode prints the top-level keys and a sample document’s keys:

```bash
adams probe --today
```

### Save cache
Results are cached to `cache/YYYY-MM-DD.json` automatically. Re-run uses the cache unless you pass `--no-cache`.

## What v1 does (by design)

- Queries APS for documents added on a given date (`DateAddedTimestamp`)
- Paginates with `skip`
- Filters obvious noise (fitness-for-duty, admin notices, etc.)
- Scores titles with a weighted keyword list (transparent, editable)
- Prints Top N with “reason tags”
- Saves a JSON cache (raw response documents)

## Roadmap (later)
- Better field mapping once you confirm schema
- Optional “modes” (enforcement / spent fuel / EP / licensing)
- Optional PDF download for top picks
- Optional trend analytics

## License
MIT
