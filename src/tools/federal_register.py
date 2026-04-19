from __future__ import annotations
"""Federal Register REST API client — paginates tariff-related documents."""

import hashlib
import time
from datetime import datetime, timezone

import httpx

_BASE_URL = "https://www.federalregister.gov/api/v1/documents"
# Only request the fields we actually use to keep payloads small
_FIELDS = ["document_number", "abstract", "title", "effective_on", "html_url", "agencies"]
_PAGE_SIZE = 20


class FederalRegisterClient:
    """Fetches tariff documents from the Federal Register REST API.

    Paginates forward until a full page contains no document_numbers that are
    absent from `seen_ids`. This means a single call will stop quickly for
    incremental polls (most documents already seen) while still catching every
    new document on a cold start.
    """

    def __init__(self, search_term: str = "tariff"):
        self.search_term = search_term

    async def fetch_tariff_documents(
        self, seen_ids: set[str]
    ) -> tuple[list[dict], list[dict]]:
        """Return (new_docs, audit_entries).

        new_docs:      Unseen documents, each with an added `content_hash` field
                       (SHA-256 of title + abstract) so callers can also detect
                       content changes on a known document_number.
        audit_entries: One entry per HTTP request, structured for agent_runs logging.
        """
        new_docs: list[dict] = []
        audit_entries: list[dict] = []
        page = 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                # httpx accepts a list of 2-tuples for repeated query params
                params = [
                    ("conditions[term]", self.search_term),
                    ("per_page", _PAGE_SIZE),
                    ("page", page),
                ] + [("fields[]", f) for f in _FIELDS]

                started_at = datetime.now(timezone.utc).isoformat()
                t0 = time.monotonic()

                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                latency_ms = int((time.monotonic() - t0) * 1000)
                results: list[dict] = data.get("results", [])
                total_pages: int = data.get("total_pages", 1)

                audit_entries.append({
                    "agent_name": "signal_monitor",
                    "model": None,
                    "input_payload": {
                        "source": "federal_register",
                        "page": page,
                        "per_page": _PAGE_SIZE,
                        "term": self.search_term,
                    },
                    "output_payload": {
                        "document_count": len(results),
                        "total_pages": total_pages,
                    },
                    "latency_ms": latency_ms,
                    "started_at": started_at,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                })

                found_new = False
                for doc in results:
                    doc_number = doc.get("document_number")
                    if doc_number and doc_number not in seen_ids:
                        found_new = True
                        # Add dedup hash so callers can key on content changes too
                        doc["content_hash"] = _content_hash(doc)
                        new_docs.append(doc)

                # Stop paginating when this page added nothing new, or we've hit the end
                if not found_new or page >= total_pages:
                    break
                page += 1

        return new_docs, audit_entries


def _content_hash(doc: dict) -> str:
    """SHA-256 of title + abstract — detects content changes on the same document_number."""
    raw = (doc.get("title") or "") + (doc.get("abstract") or "")
    return hashlib.sha256(raw.encode()).hexdigest()
