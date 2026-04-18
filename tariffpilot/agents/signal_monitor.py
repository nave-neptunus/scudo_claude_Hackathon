from __future__ import annotations
"""Signal Monitor Agent — two modes:

1. run(raw_event)           — ReAct loop; enriches a known event via Brave Search.
2. poll_federal_register()  — discovery mode; fetches new tariff documents from the
                              Federal Register REST API, extracts structured metadata
                              with Llama 3.3 70B, and returns TariffEvent dicts.
"""

import json
import time
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from groq import AsyncGroq
from pydantic import BaseModel, ValidationError

from tools.mcp_client import BraveMCPClient
from tools.federal_register import FederalRegisterClient

MODEL = "llama-3.3-70b-versatile"

# File that persists document_numbers seen across CLI runs so we don't reprocess
_SEEN_IDS_PATH = Path("data/seen_document_numbers.json")
# Append-only audit log — one JSON object per line (mirrors the agent_runs DB table)
_AGENT_RUNS_LOG = Path("output/agent_runs.jsonl")


# ---------------------------------------------------------------------------
# Pydantic model for LLM extraction output (validates before use)
# ---------------------------------------------------------------------------

class FedRegDocExtraction(BaseModel):
    """Structured metadata extracted from a Federal Register document."""
    hs_codes: list[str]
    jurisdictions: list[str]       # ISO-3166 country codes
    effective_date: Optional[str] = None   # YYYY-MM-DD or null
    rate_change_bps: Optional[int] = None  # e.g. 0% → 84% = 8400; negative = tariff cut


# ---------------------------------------------------------------------------
# Prompt for Federal Register extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """<instructions>
You are a US trade-law analyst. Given the title and abstract of a Federal Register
document, extract structured tariff metadata. Be conservative: only include values
you can reliably infer from the text. Leave fields null when uncertain.
</instructions>

<rules>
- hs_codes: list of HS/HTS code strings found in the text (e.g. "8542.31", "8542").
  Include all precision levels mentioned. Return [] if none found.
- jurisdictions: ISO-3166 two-letter country codes for the SOURCE countries affected
  by the tariff (e.g. ["CN"] for China, ["RU"] for Russia). Return [] if none found.
- effective_date: ISO date string YYYY-MM-DD of the tariff effective date, or null.
- rate_change_bps: integer basis-point change in tariff rate (100 bps = 1 percentage
  point). Positive = tariff increase, negative = decrease.
  Example: 0% → 84% = 8400. Return null if you cannot determine it confidently.
</rules>

<output_format>
Return ONLY valid JSON — no markdown, no explanation:
{
  "hs_codes": ["8542.31", "8542.39"],
  "jurisdictions": ["CN"],
  "effective_date": "2026-05-01",
  "rate_change_bps": 8400
}
</output_format>"""


# ---------------------------------------------------------------------------
# Prompt for Brave Search ReAct enrichment
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """<instructions>
You are a trade intelligence analyst specializing in tariff signal monitoring.
Your job is to enrich raw tariff event signals with verified intelligence from web searches.
You use a ReAct loop: reason about what you need to know, then call brave_search to find it,
then reason again based on results, repeat until confidence is high enough.
Stop when confidence_score >= 0.85 or after 3 search rounds.
</instructions>

<context>
You have access to the brave_search tool which returns current web search results.
Focus on: official government sources (USTR, Commerce, CBP, WTO), trade publications,
and financial research. Cross-reference multiple sources before assigning high confidence.
</context>

<task>
Enrich the tariff event with:
1. Confirmed HS codes affected (full 8-digit codes where possible)
2. Rate delta: exact old_rate_pct and new_rate_pct
3. Affected countries (source countries for the tariff)
4. Effective date (ISO format: YYYY-MM-DD)
5. Threat level: CRITICAL, HIGH, MEDIUM, or LOW
6. Confidence score 0.0-1.0 based on source quality and agreement
7. Key facts from your search rounds
</task>

<output_format>
Return ONLY valid JSON with this exact structure:
{
  "event_id": "string",
  "description": "string",
  "hs_codes": ["8542.31.00", "8542.39.00"],
  "old_rate_pct": 0.0,
  "new_rate_pct": 84.0,
  "rate_delta_pct": 84.0,
  "affected_countries": ["China"],
  "effective_date": "2026-05-01",
  "threat_level": "CRITICAL",
  "confidence_score": 0.92,
  "search_rounds_used": 2,
  "key_facts": ["fact1", "fact2"],
  "sources": ["url1", "url2"]
}
No markdown, no explanation, no code fences. Return ONLY the JSON object.
</output_format>"""

BRAVE_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "brave_search",
        "description": "Search the web for current tariff and trade policy information. Returns recent news and official government announcements.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — be specific about HS codes, countries, and tariff programs",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results (1-5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


class SignalMonitorAgent:
    def __init__(self):
        self.client = AsyncGroq()
        self.brave = BraveMCPClient()
        self.max_search_rounds = 3

    # ------------------------------------------------------------------
    # MODE 1: Brave Search ReAct enrichment
    # ------------------------------------------------------------------

    async def run(self, raw_event: dict) -> dict:
        print(f"\n[SignalMonitor] Starting ReAct loop for event: {raw_event.get('event_id', 'unknown')}")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Enrich this tariff event signal:\n{json.dumps(raw_event, indent=2)}",
            },
        ]

        search_rounds = 0
        final_result = None

        while search_rounds < self.max_search_rounds:
            response = await self.client.chat.completions.create(
                model=MODEL,
                max_tokens=4096,
                tools=[BRAVE_TOOL_DEF],
                tool_choice="auto",
                messages=messages,
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "stop" or not msg.tool_calls:
                text = msg.content or ""
                final_result = self._parse_json(text)
                if final_result:
                    final_result["search_rounds_used"] = search_rounds
                break

            if finish_reason == "tool_calls" and msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                })

                for tc in msg.tool_calls:
                    if tc.function.name == "brave_search":
                        search_rounds += 1
                        args = json.loads(tc.function.arguments)
                        query = args.get("query", "")
                        count = args.get("count", 5)
                        print(f"[SignalMonitor] Round {search_rounds}: searching → {query!r}")
                        results = await self._execute_brave_search(query, count)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(results),
                        })

                if search_rounds >= self.max_search_rounds:
                    messages.append({"role": "user", "content": "Confidence is sufficient. Return the final enriched JSON now."})
                    final_response = await self.client.chat.completions.create(
                        model=MODEL,
                        max_tokens=2048,
                        messages=messages,
                    )
                    text = final_response.choices[0].message.content or ""
                    final_result = self._parse_json(text)
                    if final_result:
                        final_result["search_rounds_used"] = search_rounds
                    break
            else:
                break

        if not final_result:
            final_result = self._fallback(raw_event, search_rounds)

        print(f"[SignalMonitor] Done. Confidence: {final_result.get('confidence_score', 0):.2f}, rounds: {final_result.get('search_rounds_used', 0)}")
        return final_result

    # ------------------------------------------------------------------
    # MODE 2: Federal Register polling
    # ------------------------------------------------------------------

    async def poll_federal_register(
        self, seen_ids: Optional[set[str]] = None
    ) -> tuple[list[dict], set[str]]:
        """Discover new tariff documents from the Federal Register REST API.

        Loads previously seen document_numbers from disk (or uses the caller-
        supplied set), fetches only new documents, runs LLM extraction on each,
        and persists the updated seen set so the next call is incremental.

        Returns:
            events:           List of TariffEvent dicts ready for the BOM Mapper.
            updated_seen_ids: The full set of seen document_numbers after this run.
        """
        if seen_ids is None:
            seen_ids = _load_seen_ids()

        fed_client = FederalRegisterClient(search_term="tariff")
        print(f"\n[SignalMonitor] Polling Federal Register (known docs: {len(seen_ids)})")

        new_docs, audit_entries = await fed_client.fetch_tariff_documents(seen_ids)
        print(f"[SignalMonitor] Found {len(new_docs)} new Federal Register document(s)")

        # Log every API call (read-only calls must still be logged)
        for entry in audit_entries:
            self._log_agent_run(entry)

        if not new_docs:
            return [], seen_ids

        # Extract structured metadata from each new document concurrently
        extraction_tasks = [self._extract_tariff_metadata(doc) for doc in new_docs]
        extractions = await asyncio.gather(*extraction_tasks, return_exceptions=True)

        events: list[dict] = []
        for doc, extraction in zip(new_docs, extractions):
            doc_number = doc["document_number"]

            if isinstance(extraction, Exception):
                print(f"[SignalMonitor] Extraction failed for {doc_number}: {extraction}")
                # Mark seen even on failure so we don't retry indefinitely
                seen_ids.add(doc_number)
                continue

            agencies = doc.get("agencies") or []
            agency_names = [a.get("name", "") for a in agencies if isinstance(a, dict)]

            event: dict = {
                "event_id": doc_number,
                "source": "federal_register",
                "published_at": doc.get("effective_on") or datetime.now(timezone.utc).isoformat(),
                "title": doc.get("title", ""),
                "url": doc.get("html_url", ""),
                "hs_codes": extraction.hs_codes,
                "jurisdictions": extraction.jurisdictions,
                "rate_change_bps": extraction.rate_change_bps,
                "effective_date": extraction.effective_date,
                "raw_excerpt": (doc.get("abstract") or "")[:2000],
                "agencies": agency_names,
                "content_hash": doc.get("content_hash", ""),
                "document_number": doc_number,
            }
            events.append(event)
            seen_ids.add(doc_number)

            print(
                f"[SignalMonitor] {doc_number}: {len(extraction.hs_codes)} HS codes, "
                f"jurisdictions={extraction.jurisdictions}"
            )

        _save_seen_ids(seen_ids)
        print(f"[SignalMonitor] Returning {len(events)} event(s) from Federal Register poll")
        return events, seen_ids

    async def _extract_tariff_metadata(self, doc: dict) -> FedRegDocExtraction:
        """Call Llama 3.3 70B to extract hs_codes/jurisdictions/date/rate from
        a Federal Register document title + abstract. Validates with Pydantic."""
        user_content = (
            f"Title: {doc.get('title', '')}\n\n"
            f"Abstract: {doc.get('abstract') or '(no abstract)'}"
        )

        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()

        response = await self.client.chat.completions.create(
            model=MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        text = response.choices[0].message.content or ""

        self._log_agent_run({
            "agent_name": "signal_monitor",
            "model": MODEL,
            "input_payload": {
                "source": "federal_register_extraction",
                "document_number": doc.get("document_number"),
            },
            "output_payload": {"raw_response": text[:500]},
            "latency_ms": latency_ms,
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })

        raw = self._parse_json(text)
        if raw is None:
            raise ValueError(f"LLM returned unparseable JSON for {doc.get('document_number')}: {text[:200]}")

        # Pydantic validates field types and coerces where safe
        return FedRegDocExtraction(**raw)

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log_agent_run(self, entry: dict) -> None:
        """Append one agent_runs record to output/agent_runs.jsonl."""
        _AGENT_RUNS_LOG.parent.mkdir(exist_ok=True)
        record = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **entry,
        }
        with _AGENT_RUNS_LOG.open("a") as f:
            f.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _execute_brave_search(self, query: str, count: int) -> list[dict]:
        return await self.brave.search(query, count)

    def _parse_json(self, text: str) -> Optional[dict]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
        return None

    def _check_confidence(self, text: str) -> float:
        if "confidence" in text.lower():
            m = re.search(r'"confidence[^"]*":\s*([0-9.]+)', text)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    pass
        return 0.0

    def _fallback(self, raw_event: dict, search_rounds: int) -> dict:
        hints = raw_event.get("hs_codes_hint", [])
        countries = raw_event.get("affected_countries_hint", ["China"])
        rate_hint = raw_event.get("rate_change_hint", "0% → 25%")
        old_r, new_r = 0.0, 25.0
        try:
            parts = rate_hint.replace("%", "").split("→")
            old_r = float(parts[0].strip())
            new_r = float(parts[1].strip())
        except Exception:
            pass
        return {
            "event_id": raw_event.get("event_id", "UNKNOWN"),
            "description": raw_event.get("description", "Unknown tariff event"),
            "hs_codes": hints or ["8542.31.00"],
            "old_rate_pct": old_r,
            "new_rate_pct": new_r,
            "rate_delta_pct": new_r - old_r,
            "affected_countries": countries,
            "effective_date": raw_event.get("effective_date_hint", "2026-05-01"),
            "threat_level": "HIGH" if (new_r - old_r) >= 25 else "MEDIUM",
            "confidence_score": 0.55,
            "search_rounds_used": search_rounds,
            "key_facts": ["Fallback enrichment — real search rounds exhausted"],
            "sources": [],
        }


# ------------------------------------------------------------------
# Persistence helpers for seen document_numbers
# ------------------------------------------------------------------

def _load_seen_ids() -> set[str]:
    """Load persisted document_numbers from disk. Returns empty set on first run."""
    if not _SEEN_IDS_PATH.exists():
        return set()
    try:
        with _SEEN_IDS_PATH.open() as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen_ids(seen_ids: set[str]) -> None:
    """Persist document_numbers to disk so the next run is incremental."""
    _SEEN_IDS_PATH.parent.mkdir(exist_ok=True)
    with _SEEN_IDS_PATH.open("w") as f:
        json.dump(sorted(seen_ids), f, indent=2)
