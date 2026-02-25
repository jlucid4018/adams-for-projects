from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from typing import Any, Dict, List, Tuple

from .aps_client import APSClient, APSClientError
from .scoring import score_title, is_noise, infer_angle, doc_bonus
from .cache import ensure_cache_dir, save_json
from .exporter import write_run_artifact

TOOL_NAME = "adams-for-projects"
TOOL_VERSION = "0.1.0"  # bump later if you want

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

def _doc_docket(doc: Dict[str, Any]) -> List[str]:
    """
    Normalize docket(s) to a list of strings for export friendliness.
    """
    v = doc.get("DocketNumber") or doc.get("docketNumber") or ""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        # sometimes multiple dockets in one string separated by commas
        parts = [p.strip() for p in v.split(",")]
        return [p for p in parts if p]
    return []

def _doc_project(doc: Dict[str, Any]) -> str:
    v = doc.get("ProjectNumber") or doc.get("projectNumber") or ""
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v).strip() if v else ""

def _doc_url(doc: Dict[str, Any]) -> str:
    return (doc.get("Url") or doc.get("url") or doc.get("ADAMSUrl") or "").strip()

def _normalize_title_for_cluster(title: str) -> str:
    t = (title or "").lower().strip()
    t = t.replace("&", "and")
    t = re.sub(r"\b(attachment|enclosure|cover letter|supplement|appendix|exhibit)\b\s*[:\-]?\s*\d*\s*", "", t)
    t = re.sub(r"\b(rev|revision)\b\s*\d+\b", "", t)
    t = re.sub(r"\b(corrected copy)\b", "", t)
    t = re.sub(r"\(epid[^)]*\)", "", t).strip()
    t = re.sub(r"\(docket[^)]*\)", "", t).strip()
    t = t.replace(" - ", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t

_EPID_RE = re.compile(r"\bEPID\s*([A-Z]-\d{4}-[A-Z]{3}-\d{4})\b", re.IGNORECASE)
_NEI_RE = re.compile(r"\bNEI\s*(\d{2})\s*-\s*(\d{2})\b", re.IGNORECASE)

def _extract_epid(title: str) -> str:
    m = _EPID_RE.search(title or "")
    return m.group(1).upper() if m else ""

def _extract_nei_id(title: str) -> str:
    m = _NEI_RE.search(title or "")
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}"

def _topic_fingerprint(best_doc: Dict[str, Any]) -> str:
    title = _doc_title(best_doc)
    epid = _extract_epid(title)
    if epid:
        return f"EPID::{epid}"
    nei = _extract_nei_id(title)
    if nei:
        return f"NEI::{nei}"
    proj = _doc_project(best_doc)
    if proj:
        return f"PROJ::{proj}"
    norm = _normalize_title_for_cluster(title)
    dockets = _doc_docket(best_doc)
    docket_hint = dockets[0] if dockets else ""
    return f"TITLE::{norm}||{docket_hint}"

def _fetch_with_fallback(client: APSClient, day: dt.date, args) -> Tuple[dt.date, List[Dict[str, Any]]]:
    """
    RECENT v1 behavior: fallback to previous day when today is empty.
    """
    attempt = 0
    cur = day
    while True:
        docs, _oldest = client.fetch_docs_added_on_date(
            cur, max_pages=args.max_pages, page_size=100, stop_when_older=True
        )
        if docs:
            if cur != day:
                print(f"[+] Using last posting day: {cur} (found {len(docs)} docs)")
            return cur, docs

        if attempt >= args.fallback_days:
            print(f"[!] No documents found for {day} and the previous {args.fallback_days} day(s).")
            return day, []

        prev = cur - dt.timedelta(days=1)
        print(f"[!] No documents found for {cur}, checking previous day ({prev}) ...")
        cur = prev
        attempt += 1

def _cluster_entries(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for d in docs:
        title = _doc_title(d)
        if not title or is_noise(title):
            continue

        score, hits = score_title(title)
        score += doc_bonus(title)

        docket_key = ",".join(_doc_docket(d))
        key = (_normalize_title_for_cluster(title), docket_key)

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
        entry["angle"] = infer_angle(_doc_title(entry["best_doc"]), entry["best_hits"])

    return sorted(clusters.values(), key=lambda e: e["best_score"], reverse=True)

def _top_topics_no_repeats(docs: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    ranked = _cluster_entries(docs)
    used: set[str] = set()
    out: List[Dict[str, Any]] = []
    for c in ranked:
        fp = _topic_fingerprint(c["best_doc"])
        if fp in used:
            continue
        used.add(fp)
        out.append(c)
        if len(out) >= top_n:
            break
    return out

def cmd_run(args) -> int:
    requested_day = _parse_requested_date(args)
    color_on = _use_color(args.color)

    print(f"[+] Fetching newest docs and filtering locally for {requested_day} (max_pages={args.max_pages}) ...")

    try:
        client = APSClient(args.key, debug=args.debug)
        used_day, all_docs = _fetch_with_fallback(client, requested_day, args)
    except APSClientError as e:
        print(f"[!] ERROR: {e}")
        return 2

    cache_dir = ensure_cache_dir("cache")
    cache_path = cache_dir / f"{used_day}.json"
    save_json(cache_path, {"requested_date": str(requested_day), "used_date": str(used_day), "docs": all_docs})
    print(f"[+] Retrieved {len(all_docs)} docs for {used_day}. Cached to {cache_path}")

    topics = _top_topics_no_repeats(all_docs, top_n=args.top)

    print(f"\nTop {args.top} topics (no repeats):")
    export_topics: List[Dict[str, Any]] = []

    for i, t in enumerate(topics, start=1):
        best = t["best_doc"]
        title = _doc_title(best)
        acc = _doc_accession(best)
        dockets = _doc_docket(best)
        score = t["best_score"]
        hits = t["best_hits"]
        files = t["accessions"]
        url = _doc_url(best)

        sev_label, sev_color = _sev_for_score(score)
        sev_txt = _paint(sev_label, sev_color, color_on)
        score_txt = _paint(f"[{score:>2}]", sev_color, color_on)

        print(f"\n#{i}  {score_txt}  {sev_txt}  {acc}  (cluster {len(files)} files){'  docket ' + ','.join(dockets) if dockets else ''}")
        print(f"     {title}")
        if hits:
            print(f"     hits: {hits}")
        print(f"     {t['angle']}")
        show = ", ".join(files[:6])
        if len(files) > 6:
            show += f", … (+{len(files)-6} more)"
        print(f"     files: {show}")
        if url:
            print(f"     url: {url}")

        # Agent-friendly topic entry
        sev_name = sev_label.split(":", 1)[1] if ":" in sev_label else sev_label
        export_topics.append({
            "rank": i,
            "score": score,
            "severity": sev_name,
            "title": title,
            "angle": t["angle"],
            "hits": hits,
            "dockets": dockets,
            "accessions": files,
            "best_accession": acc,
            "urls": [u for u in [url] if u],
        })

    # Export run artifact JSON
    if args.export_json:
        out_path = write_run_artifact(
            export_dir=args.export_dir,
            tool_name=TOOL_NAME,
            version=TOOL_VERSION,
            mode="recent",
            requested_date=str(requested_day),
            used_date=str(used_day),
            max_pages=args.max_pages,
            page_size=100,
            fallback_days=args.fallback_days,
            docs_total_for_used_date=len(all_docs),
            topics=export_topics,
        )
        print(f"\n[+] Exported run artifact: {out_path}")

    return 0

def cmd_probe(args) -> int:
    requested_day = _parse_requested_date(args)
    try:
        client = APSClient(args.key, debug=args.debug)
        used_day, docs = _fetch_with_fallback(client, requested_day, args)
    except APSClientError as e:
        print(f"[!] ERROR: {e}")
        return 2
    print(f"[+] requested={requested_day} used={used_day} docs={len(docs)}")
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
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="ANSI color output")

    # NEW: export
    p.add_argument("--export-json", action="store_true", help="Write an agent-friendly JSON artifact to reports/")
    p.add_argument("--export-dir", default="reports", help="Export directory for run artifacts (default: reports)")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="Probe daily docs (with fallback)").set_defaults(func=cmd_probe)
    sub.add_parser("run", help="Rank docs (with fallback + no repeats)").set_defaults(func=cmd_run)
    return p

def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.key:
        raise SystemExit("No APS key provided. Set APS_KEY env var or pass --key.")
    raise SystemExit(args.func(args))
