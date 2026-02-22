from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List, Optional, Tuple

import requests

APS_SEARCH_URL = "https://adams-api.nrc.gov/aps/api/search"


class APSClientError(RuntimeError):
    pass


class APSClient:
    """
    APS client tuned for the NRC deployment you've got:
      - Response schema: {count, results:[{document:{...}}], facets, pageNumber}
      - Backend is picky about request body shape and may 500 on "minimal" payloads.
      - WORKAROUND: pull newest docs (sorted) using the legacy/compatible body, then filter locally by date.
    """

    def __init__(self, api_key: str, debug: bool = False, base_url: str = APS_SEARCH_URL):
        self.api_key = api_key
        self.debug = debug
        self.base_url = base_url
        self.session = requests.Session()
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": api_key,
            "Cache-Control": "no-cache",
        }

    def _dump_last(self, body: Dict[str, Any], resp: requests.Response) -> None:
        try:
            with open(".adamsfp_last_request.json", "w", encoding="utf-8") as f:
                json.dump(body, f, indent=2, ensure_ascii=False)
            with open(".adamsfp_last_response.txt", "w", encoding="utf-8") as f:
                f.write(resp.text or "")
        except Exception:
            pass

    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        # Hard timeouts so it never "hangs"
        resp = self.session.post(
            self.base_url,
            headers=self.headers,
            json=body,
            timeout=(5, 20),
        )
        if self.debug:
            print(f"[debug] POST {self.base_url} HTTP {resp.status_code}")

        if resp.status_code >= 400:
            self._dump_last(body, resp)

        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def extract_docs(payload: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]], Optional[int]]:
        count = payload.get("count") if isinstance(payload.get("count"), int) else None
        page_num = payload.get("pageNumber") if isinstance(payload.get("pageNumber"), int) else None

        docs: List[Dict[str, Any]] = []
        if isinstance(payload.get("results"), list):
            for it in payload["results"]:
                if isinstance(it, dict) and isinstance(it.get("document"), dict):
                    docs.append(it["document"])
            return (count or len(docs), docs, page_num)

        # fallback legacy list keys (just in case)
        for key in ("Documents", "documents", "Results", "results", "items"):
            if isinstance(payload.get(key), list):
                docs = payload[key]
                total = None
                for tkey in ("total", "Total", "totalCount", "TotalCount", "count", "Count"):
                    if isinstance(payload.get(tkey), int):
                        total = payload[tkey]
                        break
                return (total or len(docs), docs, page_num)

        return (count or 0, [], page_num)

    @staticmethod
    def _date_added_prefix(doc: Dict[str, Any]) -> str:
        # We only need YYYY-MM-DD prefix for comparisons
        for k in ("dateAddedTimestamp", "DateAddedTimestamp", "dateAdded", "DateAdded"):
            v = doc.get(k)
            if isinstance(v, str) and len(v) >= 10:
                return v[:10]
        return ""

    def search_latest_legacy(self, skip: int = 0) -> Dict[str, Any]:
        """
        Use the 'legacy/compatible' body shape that this backend accepts.
        (Your earlier successful response came back with count/results on this style.)
        """
        body = {
            "q": "",
            "filters": [],          # IMPORTANT: backend expects these keys to exist
            "anyFilters": [],
            "mainLibFilter": True,
            "legacyLibFilter": False,
            "sort": "DateAddedTimestamp",
            "sortDirection": -1,
            "skip": skip,
        }
        return self._post(body)

    def fetch_docs_added_on_date(
        self,
        day: dt.date,
        max_pages: int = 10,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Pull newest pages and keep docs whose DateAddedTimestamp date == day.
        Stop early once we fall below the target day.
        """
        target = day.strftime("%Y-%m-%d")
        kept: List[Dict[str, Any]] = []

        for page in range(max_pages):
            skip = page * page_size
            if self.debug:
                print(f"[debug] Fetch newest page {page+1}/{max_pages} skip={skip} pageSize={page_size}")

            payload = self.search_latest_legacy(skip=skip)
            _count, docs, _pn = self.extract_docs(payload)
            if not docs:
                break

            below_day = False
            for d in docs:
                dday = self._date_added_prefix(d)
                if dday == target:
                    kept.append(d)
                elif dday and dday < target:
                    below_day = True

            # Once we see older-than-target docs, the rest will be older too
            if below_day:
                break

            # If fewer than a full page returned, we're done
            if len(docs) < page_size:
                break

        return kept
