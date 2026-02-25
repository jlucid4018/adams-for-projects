from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from typing import Any, Dict, List, Tuple

from .aps_client import APSClient, APSClientError
from .scoring import score_title, is_noise, infer_angle, doc_bonus
from .cache import ensure_cache_dir, save_json

ANSI = {
    "reset": "\x1b[0m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "bright_yellow": "\x1b[93m",
    "gray": "\x1b[90m",
}

def _use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()

def _paint(s: str, color: str, enabled: bool) -> str:
    if not enabled:
        return s
    return f"{ANSI.get(color,'')}{s}{ANSI['reset']}"

def _sev_for_score(score: int) -> Tuple[str, str]:
    if score >= 28:
        return ("SEV:CRITICAL", "red")
    if score >= 22:
        return ("SEV:VERY_HIGH", "bright_yellow")
    if score >= 14:
        return ("SEV:HIGH", "yellow")
    if score >= 8:
        return ("SEV:MED", "green")
    return ("SEV:LOW", "gray")

def _parse_requested_date(args) -> dt.date:
    if getattr(args, "today", False):
        return dt.date.today()
    if getattr(args, "date", None):
        return dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    return dt.date.today()

def _doc_title(doc: Dict[str, Any]) -> str:
    return (doc.get("DocumentTitle") or doc.get("documentTitle") or doc.get("title") or "").strip()

def _doc_accession(doc: Dict[str, Any]) -> str:
    return (doc.get("AccessionNumber") or doc.get("accessionNumber") or doc.get("accession") or "").strip()

def _doc_docket(doc: Dict[str, Any]) -> str:
    v = doc.get("DocketNumber") or doc.get("docketNumber") or ""
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip() if v else ""

def _fetch_recent_with_fallback(client: APSClient, requested: dt.date, args) -> Tuple[dt.date, List[Dict[str, Any]], Optional[dt.date]]:
    """
    RECENT mode: weekend/holiday fallback allowed.
    """
    attempt = 0
    cur = requested
    while True:
        docs, oldest_seen = client.fetch_docs_added_on_date(
            cur, max_pages=args.max_pages, page_size=100, stop_when_older=True
        )
        if docs:
            if cur != requested:
                print(f"[+] Using last posting day: {cur} (found {len(docs)} docs)")
            return cur, docs, oldest_seen

        if attempt >= args.fallback_days:
            print(f"[!] No documents found for {requested} and the previous {args.fallback_days} day(s).")
            return requested, [], oldest_seen

        prev = cur - dt.timedelta(days=1)
        print(f"[!] No documents found for {cur}, checking previous day ({prev}) ...")
        cur = prev
        attempt += 1

def _fetch_archive_no_fallback(client: APSClient, requested: dt.date, args) -> Tuple[dt.date, List[Dict[str, Any]], Optional[dt.date]]:
    """
    ARCHIVE mode: no fallback. Best-effort scanning within newest window.
    """
    docs, oldest_seen = client.fetch_docs_added_on_date(
        requested, max_pages=args.max_pages, page_size=100, stop_when_older=False
    )
    if not docs and oldest_seen is not None and requested < oldest_seen:
        print(f"[!] No matches for {requested} within newest window scanned.")
        print(f"[!] Oldest date seen in scanned window: {oldest_seen}")
        print("[!] Archive mode v2 is best-effort until server-side date-range search is implemented.")
        print("[!] Increase --max-pages for near-recent dates, or implement server-side date filtering in v2.1+.")
    return requested, docs, oldest_seen

def _cluster_entries(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keep v1 clustering behavior (you already have NEI/EPID family logic in your current build).
    If you want the latest NEI/EPID fingerprint version, keep using that cli.py build.
    This v2 patch focuses on mode behavior without breaking output.
    """
    clusters: List[Dict[str, Any]] = []

    # simple “best doc only” for v2 scaffolding; keep your existing dedupe build if you prefer
    for d in docs:
        title = _doc_title(d)
        if not title or is_noise(title):
            continue
        score, hits = score_title(title)
        score += doc_bonus(title)
        clusters.append({
            "best_doc": d,
            "best_score": score,
            "best_hits": hits,
            "angle": infer_angle(title, hits),
            "accessions": [_doc_accession(d) or "UNKNOWN"],
        })

    clusters.sort(key=lambda x: x["best_score"], reverse=True)
    return clusters

def cmd_run(args) -> int:
    requested_day = _parse_requested_date(args)
    color_on = _use_color(args.color)

    print(f"[+] MODE={args.mode.upper()}  requested={requested_day}  max_pages={args.max_pages}")

    try:
        client = APSClient(args.key, debug=args.debug)
        if args.mode == "recent":
            used_day, docs, oldest_seen = _fetch_recent_with_fallback(client, requested_day, args)
        else:
            used_day, docs, oldest_seen = _fetch_archive_no_fallback(client, requested_day, args)
    except APSClientError as e:
        print(f"[!] ERROR: {e}")
        return 2

    cache_dir = ensure_cache_dir("cache")
    cache_path = cache_dir / f"{used_day}.json"
    save_json(cache_path, {"requested_date": str(requested_day), "used_date": str(used_day), "docs": docs})
    print(f"[+] Retrieved {len(docs)} docs for {used_day}. Cached to {cache_path}")

    topics = _cluster_entries(docs)[:args.top]

    print(f"\nTop {args.top} topics:")
    for i, t in enumerate(topics, start=1):
        best = t["best_doc"]
        title = _doc_title(best)
        acc = _doc_accession(best)
        docket = _doc_docket(best)
        score = t["best_score"]
        hits = t["best_hits"]

        sev_label, sev_color = _sev_for_score(score)
        sev_txt = _paint(sev_label, sev_color, color_on)
        score_txt = _paint(f"[{score:>2}]", sev_color, color_on)

        url = best.get("Url") or best.get("url") or ""

        print(f"\n#{i}  {score_txt}  {sev_txt}  {acc}{'  docket ' + docket if docket else ''}")
        print(f"     {title}")
        if hits:
            print(f"     hits: {hits}")
        print(f"     {t['angle']}")
        if url:
            print(f"     url: {url}")

    return 0

def cmd_probe(args) -> int:
    requested_day = _parse_requested_date(args)
    try:
        client = APSClient(args.key, debug=args.debug)
        if args.mode == "recent":
            used_day, docs, oldest_seen = _fetch_recent_with_fallback(client, requested_day, args)
        else:
            used_day, docs, oldest_seen = _fetch_archive_no_fallback(client, requested_day, args)
    except APSClientError as e:
        print(f"[!] ERROR: {e}")
        return 2

    print(f"[+] MODE={args.mode.upper()} requested={requested_day} used={used_day} docs={len(docs)} oldest_seen={oldest_seen}")
    if docs:
        print("[+] Sample keys:", list(docs[0].keys()))
        print("    accession:", _doc_accession(docs[0]))
        print("    title:", _doc_title(docs[0])[:140])
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adams", description="ADAMS for Projects: daily APS scanner")
    p.add_argument("--key", default=os.environ.get("APS_KEY", ""), help="APS subscription key (or set APS_KEY env var)")
    p.add_argument("--mode", choices=("recent", "archive"), default="recent", help="Mode: recent (default) or archive (no fallback)")
    p.add_argument("--today", action="store_true", help="Use today's date")
    p.add_argument("--date", help="Use a specific date YYYY-MM-DD")
    p.add_argument("--top", type=int, default=5, help="How many top topics to display")
    p.add_argument("--max-pages", type=int, default=10, help="Safety cap on newest pages fetched (page size=100)")
    p.add_argument("--fallback-days", type=int, default=7, help="RECENT mode: if 0 docs, check previous days up to this many")
    p.add_argument("--debug", action="store_true", help="Verbose debug output")
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="ANSI color output")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="Probe (with mode behavior)").set_defaults(func=cmd_probe)
    sub.add_parser("run", help="Run (with mode behavior)").set_defaults(func=cmd_run)
    return p

def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.key:
        raise SystemExit("No APS key provided. Set APS_KEY env var or pass --key.")
    raise SystemExit(args.func(args))
