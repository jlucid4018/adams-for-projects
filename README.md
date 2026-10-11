# ADAMS for Projects

A small CLI for finding public NRC ADAMS records worth reading. It retrieves posting-day metadata from the APS API, falls back to a recent posting day when necessary, groups related records, and produces a short reading list with source links.

## What changed in 0.2.0

Version 2.0.0 of the review classifier replaces additive keyword scores for selection. Output uses **High**, **Medium**, and **Background** reading priority, document types, factual title-based reasons, and separate thematic tags. Legacy scores, severity labels, keyword hits, and editorial angles remain in JSON for comparison. They do not drive current rankings. See [review methodology](docs/review-priority.md) for the rules and limitations.

## Install

Python 3.10 or newer and an NRC APS subscription key are required.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
export APS_KEY="YOUR_KEY_HERE"
```

Global flags come before the subcommand:

```sh
adams --today probe
adams --today --top 5 run
adams --date 2026-02-25 --top 10 run
adams --today --color never --export-json run
```

Console output includes review priority, document type, the reason for selection, the representative accession, related accessions, docket hints, and source URL. Daily metadata is cached to `cache/YYYY-MM-DD.json`; `--export-json` writes a dated report and `reports/latest.run.json`. Cache persistence and historical archival retention depend on the environment running the collector.

## Verify

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

This is an independent project, not affiliated with the U.S. NRC. Title-based reading priority is not an official NRC finding or a safety-severity assessment. Consult the underlying records. License: MIT; see LICENSE and NOTICE.
