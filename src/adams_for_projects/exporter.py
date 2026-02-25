from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

def _utc_now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def write_run_artifact(
    *,
    export_dir: str | Path,
    tool_name: str,
    version: str,
    mode: str,
    requested_date: str,
    used_date: str,
    max_pages: int,
    page_size: int,
    fallback_days: int,
    docs_total_for_used_date: int,
    topics: List[Dict[str, Any]],
) -> Path:
    """
    Writes an agent-friendly JSON artifact:
      reports/YYYY-MM-DD.run.json
    And also writes:
      reports/latest.run.json
    """
    out_dir = ensure_dir(export_dir)
    used = used_date  # "YYYY-MM-DD"

    artifact: Dict[str, Any] = {
        "tool": tool_name,
        "version": version,
        "mode": mode,
        "requested_date": requested_date,
        "used_date": used,
        "generated_at": _utc_now_iso(),
        "source": {
            "api": "APS",
            "page_size": page_size,
            "max_pages": max_pages,
            "fallback_days": fallback_days,
        },
        "summary": {
            "docs_total_for_used_date": docs_total_for_used_date,
            "topics_returned": len(topics),
        },
        "topics": topics,
    }

    path = out_dir / f"{used}.run.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    latest = out_dir / "latest.run.json"
    with latest.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    return path
