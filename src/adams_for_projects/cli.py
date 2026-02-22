from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from typing import Any, Dict, List, Tuple

from .aps_client import APSClient, APSClientError
from .scoring import score_title, is_noise, infer_angle, doc_bonus
from .cache import ensure_cache_dir, save_json


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
    """
    DocketNumber is sometimes a string, sometimes a list. Normalize to a printable string.
    """
    v = doc.get("DocketNumber") or doc.get("docketNumber") or ""
    if isinstance(v, list):
        parts = []
        for x in v:
            s = str(x).strip()
            if s:
                parts.append(s)
        return ", ".join(parts)
    if isinstance(v, str):
        return v.strip()
    return str(v).strip() if v else ""


def _normalize_title_for_cluster(title: str) -> str:
    t = (title or "").lower().strip()
    t = re.sub(r"\b(attachment|enclosure|cover letter|supplement|appendix|exhibit)\b\s*[:\-]?\s*\d*\s*", "", t)
    t = re.sub(r"\b(rev|revision)\b\s*\d+\b", "", t)
    t = re.sub(r"\b(corrected copy)\b", "", t)
    t = re.sub(r"\(epid[^)]*\)", "", t).strip()
    t = re.sub(r"\(docket[^)]*\)", "", t).strip()
    t = t.replace(" - ", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _fetch_with_fallback(
    client: APSClient,
    day: dt.date,
    max_pages: int,
    page_size: int,
    fallback_days: int,
    debug: bool,
) -> Tuple[dt.date, List[Dict[str, Any]]]:
    attempt = 0
    cur = day

    while True:
        if debug:
            print(f"[debug] Attempt {attempt+1}: fetching docs for {cur} ...")
        docs = client.fetch_docs_added_on_date(cur, max_pages=max_pages, page_size=page_size)

        if docs:
            if cur != day:
                print(f"[+] Using last posting day: {cur} (found {len(docs)} docs)")
            return cur, docs

        if attempt >= fallback_days:
            print(f"[!] No documents found for {day} and the previous {fallback_days} day(s).")
            return day, []

        prev = cur - dt.timedelta(days=1)
        print(f"[!] No documents found for {cur}, checking previous day ({prev}) ...")
        cur = prev
        attempt += 1


def _cluster_and_rank(docs: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    clusters: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for d in docs:
        title = _doc_title(d)
        if not title or is_noise(title):
            continue

        score, hits = score_title(title)
        score += doc_bonus(title)

        docket = _doc_docket(d) or ""
        key = (_normalize_title_for_cluster(title), docket)

        acc = _doc_accession(d) or "UNKNOWN"
        entry = clusters.get(key)
        if entry is None:
            clusters[key] = {
                "best_score": score,
                "best_hits": hits,
                "best_doc": d,
                "accessions": [acc],
            }
        else:
            entry["accessions"].append(acc)
            if score > entry["best_score"]:
                entry["best_score"] = score
                entry["best_hits"] = hits
                entry["best_doc"] = d

    for entry in clusters.values():
        best_title = _doc_title(entry["best_doc"])
        entry["angle"] = infer_angle(best_title, entry["best_hits"])

    ranked = sorted(clusters.values(), key=lambda e: e["best_score"], reverse=True)
    return ranked[:top_n]


def cmd_probe(args) -> int:
    requested_day = _parse_requested_date(args)
    print(f"[+] PROBE: fetching newest docs then filtering locally for dateAdded={requested_day} ...")

    try:
        client = APSClient(args.key, debug=args.debug)
        chosen_day, docs = _fetch_with_fallback(
            client=client,
            day=requested_day,
            max_pages=args.max_pages,
            page_size=100,
            fallback_days=args.fallback_days,
            debug=args.debug,
        )
    except APSClientError as e:
        print(f"[!] ERROR: {e}")
        return 2

    print(f"[+] Docs kept for {chosen_day}: {len(docs)}")
    if docs:
        print("[+] Sample doc keys:", list(docs[0].keys()))
        print("    accession:", _doc_accession(docs[0]))
        print("    title:", _doc_title(docs[0])[:160])
    return 0


def cmd_run(args) -> int:
    requested_day = _parse_requested_date(args)
    top_n = args.top
    print(f"[+] Fetching newest docs and filtering locally for {requested_day} (max_pages={args.max_pages}) ...")

    try:
        client = APSClient(args.key, debug=args.debug)
        chosen_day, all_docs = _fetch_with_fallback(
            client=client,
            day=requested_day,
            max_pages=args.max_pages,
            page_size=100,
            fallback_days=args.fallback_days,
            debug=args.debug,
        )
    except APSClientError as e:
        print(f"[!] ERROR: {e}")
        return 2

    cache_dir = ensure_cache_dir("cache")
    cache_path = cache_dir / f"{chosen_day}.json"
    save_json(cache_path, {"requested_date": str(requested_day), "used_date": str(chosen_day), "docs": all_docs})
    print(f"[+] Retrieved {len(all_docs)} docs for {chosen_day}. Cached to {cache_path}")

    topics = _cluster_and_rank(all_docs, top_n=top_n)

    print(f"\nTop {top_n} topics:")
    for i, t in enumerate(topics, start=1):
        best_doc = t["best_doc"]
        best_title = _doc_title(best_doc)
        best_acc = _doc_accession(best_doc)
        docket = _doc_docket(best_doc)
        hits = t["best_hits"]
        score = t["best_score"]
        accs = t["accessions"]

        print(f"\n#{i}  [{score:>3}]  {best_acc}  (cluster {len(accs)} files){'  docket ' + docket if docket else ''}")
        print(f"     {best_title}")
        if hits:
            print(f"     hits: {hits}")
        print(f"     {t['angle']}")
        show = ", ".join(accs[:6])
        if len(accs) > 6:
            show += f", … (+{len(accs)-6} more)"
        print(f"     files: {show}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adams", description="ADAMS for Projects: daily APS scanner")
    p.add_argument("--key", default=os.environ.get("APS_KEY", ""), help="APS subscription key (or set APS_KEY env var)")
    p.add_argument("--today", action="store_true", help="Use today's date")
    p.add_argument("--date", help="Use a specific date YYYY-MM-DD")
    p.add_argument("--top", type=int, default=5, help="How many top topics to display")
    p.add_argument("--max-pages", type=int, default=10, help="Safety cap on pages fetched (page size=100)")
    p.add_argument("--fallback-days", type=int, default=7, help="If 0 docs, check previous days up to this many")
    p.add_argument("--debug", action="store_true", help="Verbose debug output")

    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("probe", help="Probe by pulling newest docs and filtering locally (with fallback)")
    sp.set_defaults(func=cmd_probe)

    sr = sub.add_parser("run", help="Fetch and rank docs (clustered topics, with fallback if today is empty)")
    sr.set_defaults(func=cmd_run)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.key:
        raise SystemExit("No APS key provided. Set APS_KEY env var or pass --key.")
    rc = args.func(args)
    raise SystemExit(rc)
