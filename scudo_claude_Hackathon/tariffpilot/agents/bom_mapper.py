"""BOM Mapper Agent — two responsibilities:

1. lookup_tariff_rate(product_description)
   Cleans a raw BOM description with Claude, resolves an HTS code via the
   Census Bureau Schedule B API, then fetches live tariff rates from the
   USITC HTS API. No local caching — every call is live.

2. run(enriched_event, bom)
   Cross-references the tariff event against the full BOM. Rows that are
   missing an hs_code are enriched through lookup_tariff_rate() first, then
   all rows are sent to Claude in parallel chunks for impact scoring.
"""

import os
import json
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import anthropic
from pydantic import BaseModel, ValidationError

MODEL = "claude-sonnet-4-6"
CHUNK_SIZE = 50

_AGENT_RUNS_LOG = Path("output/agent_runs.jsonl")
_CENSUS_URL = "https://uscensus.prod.3ceonline.com/ui/api/schedulebs"
_USITC_URL = "https://hts.usitc.gov/api/search"


# ---------------------------------------------------------------------------
# Pydantic models — validated before any result crosses a function boundary
# ---------------------------------------------------------------------------

class CleanedDescription(BaseModel):
    trade_description: str  # concise, model-number-free trade terminology


class ScheduleBMatch(BaseModel):
    hs_code: str     # best-match Schedule B / HTS code, e.g. "8542.31"
    description: str
    confidence: float  # 0.0–1.0; derived from API score or position rank


class HTSRates(BaseModel):
    hts_code: str
    hts_description: str
    general_rate: str    # MFN / Column 1 General rate (e.g. "Free" or "3.5%")
    special_rates: str   # FTA / GSP rates string
    column2_rate: str    # Column 2 rate for non-MFN countries (e.g. "35%")


class TariffRateLookup(BaseModel):
    """Full chain result: description → HTS code → live rates."""
    original_description: str
    cleaned_description: str
    hs_code: str
    hts_description: str
    general_rate: str
    special_rates: str
    column2_rate: str
    schedule_b_confidence: float


# ---------------------------------------------------------------------------
# Description-cleaning prompt
# ---------------------------------------------------------------------------

DESCRIPTION_CLEANER_SYSTEM = """<instructions>
You are a US trade classification specialist. Given a raw BOM product description
(often contains internal model numbers, SKU codes, brand names, specs), return a
concise, trade-standard product description suitable for US Census Bureau Schedule B
commodity classification.
</instructions>

<rules>
- Remove internal model numbers, SKU codes, and brand names (e.g. strip "IC-8542-001", "Model X3")
- Keep the core product type using international trade terminology
- Be specific about material, function, and technical category
- Maximum 10 words
- Example input:  "Application Processor SoC IC-8542-001"
  Example output: "Integrated circuit, application processor"
</rules>

<output_format>
Return ONLY valid JSON — no markdown, no explanation:
{"trade_description": "Integrated circuit, application processor"}
</output_format>"""

# ---------------------------------------------------------------------------
# Existing chunk-analysis prompt (unchanged)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """<instructions>
You are a supply chain cost analyst. Given a tariff event and a chunk of BOM SKUs,
identify which SKUs are affected and calculate the financial impact.
</instructions>

<context>
Match HS codes at 8-digit, 6-digit, 4-digit, and 2-digit parent levels (cascade match).
Only flag SKUs whose supplier_country is in the tariff's affected_countries list AND
whose hs_code matches the tariff hs_codes at any precision level.
</context>

<task>
For each affected SKU, calculate:
  annual_tariff_impact_usd = annual_spend_usd * (rate_delta_pct / 100)
Assign severity:
  CRITICAL if annual_tariff_impact_usd > 500000
  HIGH     if annual_tariff_impact_usd > 100000
  MEDIUM   if annual_tariff_impact_usd > 10000
  LOW      otherwise
</task>

<output_format>
Return ONLY valid JSON array. Each element:
{
  "sku": "string",
  "description": "string",
  "hs_code": "string",
  "supplier": "string",
  "supplier_country": "string",
  "annual_spend_usd": 0.0,
  "annual_tariff_impact_usd": 0.0,
  "severity": "CRITICAL",
  "match_level": "8-digit",
  "has_domestic_alt": true,
  "alt_supplier": "string or null",
  "lead_time_weeks": 0,
  "critical_path": true
}
No markdown, no explanation. Return ONLY the JSON array (may be empty []).
</output_format>"""


class BOMMapperAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic()
        self.census_api_key = os.getenv("CENSUS_API_KEY", "")

    # ------------------------------------------------------------------
    # Public entry point — full BOM analysis
    # ------------------------------------------------------------------

    async def run(self, enriched_event: dict, bom: list[dict]) -> dict:
        print(f"\n[BOMMapper] Mapping {len(bom)} SKUs against tariff event")

        # Enrich rows missing hs_code before sending them to the chunk analyzer.
        # We run all lookups concurrently; rows that already have hs_code are skipped.
        bom = await self._enrich_missing_hs_codes(bom)

        chunks = [bom[i:i + CHUNK_SIZE] for i in range(0, len(bom), CHUNK_SIZE)]
        print(f"[BOMMapper] Processing {len(chunks)} chunk(s) of ≤{CHUNK_SIZE} SKUs each")

        chunk_results = await asyncio.gather(
            *[self._process_chunk(enriched_event, chunk, idx) for idx, chunk in enumerate(chunks)],
            return_exceptions=True,
        )

        affected = []
        for r in chunk_results:
            if isinstance(r, Exception):
                print(f"[BOMMapper] Chunk error (skipped): {r}")
                continue
            if isinstance(r, list):
                affected.extend(r)

        affected.sort(key=lambda x: x.get("annual_tariff_impact_usd", 0), reverse=True)

        total_impact = sum(s.get("annual_tariff_impact_usd", 0) for s in affected)
        critical_count = sum(1 for s in affected if s.get("severity") == "CRITICAL")
        high_count = sum(1 for s in affected if s.get("severity") == "HIGH")

        print(f"[BOMMapper] Found {len(affected)} affected SKUs, total impact: ${total_impact:,.0f}/yr")

        return {
            "affected_skus": affected,
            "total_annual_tariff_impact_usd": total_impact,
            "affected_sku_count": len(affected),
            "total_sku_count": len(bom),
            "severity_breakdown": {
                "CRITICAL": critical_count,
                "HIGH": high_count,
                "MEDIUM": sum(1 for s in affected if s.get("severity") == "MEDIUM"),
                "LOW": sum(1 for s in affected if s.get("severity") == "LOW"),
            },
        }

    async def _enrich_missing_hs_codes(self, bom: list[dict]) -> list[dict]:
        """For rows without an hs_code, call lookup_tariff_rate() to fill one in.

        Runs all lookups concurrently. Rows that already carry an hs_code are
        left untouched so we don't burn unnecessary API quota.
        """
        rows_to_enrich = [(i, row) for i, row in enumerate(bom) if not row.get("hs_code")]
        if not rows_to_enrich:
            return bom

        print(f"[BOMMapper] Enriching {len(rows_to_enrich)} row(s) missing hs_code via Census + USITC")

        tasks = [self.lookup_tariff_rate(row["description"]) for _, row in rows_to_enrich]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        bom = list(bom)  # shallow copy so we don't mutate the caller's list
        for (i, row), result in zip(rows_to_enrich, results):
            if isinstance(result, Exception):
                print(f"[BOMMapper] lookup_tariff_rate failed for '{row.get('sku', '?')}': {result}")
                continue
            # Patch the row with the resolved code and rate data for the chunk analyzer
            bom[i] = {
                **row,
                "hs_code": result.hs_code,
                "live_general_rate": result.general_rate,
                "live_column2_rate": result.column2_rate,
                "schedule_b_confidence": result.schedule_b_confidence,
            }
            print(
                f"[BOMMapper] '{row.get('sku', '?')}' → {result.hs_code} "
                f"(confidence={result.schedule_b_confidence:.2f}, rate={result.general_rate})"
            )

        return bom

    # ------------------------------------------------------------------
    # lookup_tariff_rate — the Census → USITC chain
    # ------------------------------------------------------------------

    async def lookup_tariff_rate(self, product_description: str) -> TariffRateLookup:
        """Clean description → Census Schedule B → USITC HTS rates.

        All three sub-steps are live calls; no local caching.
        Each sub-call is logged to agent_runs.
        """
        cleaned = await self._clean_description(product_description)
        match = await self._census_schedule_b_lookup(cleaned)
        rates = await self._usitc_hts_lookup(match.hs_code)

        return TariffRateLookup(
            original_description=product_description,
            cleaned_description=cleaned,
            hs_code=match.hs_code,
            hts_description=rates.hts_description,
            general_rate=rates.general_rate,
            special_rates=rates.special_rates,
            column2_rate=rates.column2_rate,
            schedule_b_confidence=match.confidence,
        )

    async def _clean_description(self, raw_description: str) -> str:
        """Call claude-sonnet-4-6 to standardize a raw BOM description into
        trade-standard terminology suitable for Schedule B lookup."""
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=128,
            system=DESCRIPTION_CLEANER_SYSTEM,
            messages=[{"role": "user", "content": raw_description}],
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        text = _extract_text(response)

        self._log_agent_run({
            "agent_name": "bom_mapper",
            "model": MODEL,
            "input_payload": {"step": "description_cleaner", "raw_description": raw_description},
            "output_payload": {"raw_response": text[:200]},
            "latency_ms": latency_ms,
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })

        raw = _parse_json(text)
        if raw is None:
            # Fall back to truncating the raw description rather than failing
            print(f"[BOMMapper] Description cleaner returned bad JSON for '{raw_description[:50]}', using raw")
            return raw_description[:80]

        try:
            return CleanedDescription(**raw).trade_description
        except ValidationError:
            return raw_description[:80]

    async def _census_schedule_b_lookup(self, cleaned_description: str) -> ScheduleBMatch:
        """Submit cleaned description to Census Bureau Schedule B API and return
        the top HTS code candidate with a derived confidence score."""
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()

        params: list[tuple] = [("q", cleaned_description), ("format", "json")]
        if self.census_api_key:
            params.append(("key", self.census_api_key))

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(_CENSUS_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._log_agent_run({
                "agent_name": "bom_mapper",
                "model": None,
                "input_payload": {"step": "census_schedule_b", "query": cleaned_description},
                "output_payload": {"error": str(exc)},
                "latency_ms": latency_ms,
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"[BOMMapper] Census API error: {exc} — falling back to description-based code")
            # Return a low-confidence fallback rather than raising, so the pipeline continues
            return ScheduleBMatch(hs_code="9999.99", description=cleaned_description, confidence=0.0)

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Parse defensively — the Census API has changed its response envelope before
        results: list[dict] = (
            data.get("scheduleBResults")        # known production format
            or data.get("results")
            or (data if isinstance(data, list) else [])
        )

        self._log_agent_run({
            "agent_name": "bom_mapper",
            "model": None,
            "input_payload": {"step": "census_schedule_b", "query": cleaned_description},
            "output_payload": {"result_count": len(results)},
            "latency_ms": latency_ms,
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })

        if not results:
            return ScheduleBMatch(hs_code="9999.99", description=cleaned_description, confidence=0.0)

        # Take the top result; treat score/relevance as confidence (normalize to 0–1 if > 1)
        top = results[0]
        raw_code = str(
            top.get("scheduleBCode") or top.get("hts_code") or top.get("code") or "9999.99"
        )
        # Format as dotted notation, e.g. "8542310000" → "8542.31"
        hs_code = _normalize_hts_code(raw_code)

        raw_score = float(top.get("score") or top.get("confidence") or 1.0)
        confidence = min(raw_score / 100.0, 1.0) if raw_score > 1.0 else raw_score

        return ScheduleBMatch(
            hs_code=hs_code,
            description=str(top.get("description") or cleaned_description),
            confidence=confidence,
        )

    async def _usitc_hts_lookup(self, hts_code: str) -> HTSRates:
        """Query the USITC HTS API for the live general, special, and Column 2
        tariff rates for the given HTS code. No API key required."""
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(_USITC_URL, params={"query": hts_code})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._log_agent_run({
                "agent_name": "bom_mapper",
                "model": None,
                "input_payload": {"step": "usitc_hts", "hts_code": hts_code},
                "output_payload": {"error": str(exc)},
                "latency_ms": latency_ms,
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"[BOMMapper] USITC API error for {hts_code}: {exc} — using unknown rates")
            return HTSRates(
                hts_code=hts_code, hts_description="Unknown",
                general_rate="Unknown", special_rates="", column2_rate="Unknown",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        # The USITC API may wrap results in {"content": [...]} or return a bare list
        entries: list[dict] = (
            data.get("content")
            or (data if isinstance(data, list) else [])
        )

        self._log_agent_run({
            "agent_name": "bom_mapper",
            "model": None,
            "input_payload": {"step": "usitc_hts", "hts_code": hts_code},
            "output_payload": {"entry_count": len(entries)},
            "latency_ms": latency_ms,
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })

        if not entries:
            return HTSRates(
                hts_code=hts_code, hts_description="Not found in HTS",
                general_rate="Unknown", special_rates="", column2_rate="Unknown",
            )

        # Prefer exact code match; fall back to first result
        match = next(
            (e for e in entries if str(e.get("htsno", "")).startswith(hts_code.replace(".", "")[:6])),
            entries[0],
        )

        return HTSRates(
            hts_code=str(match.get("htsno") or hts_code),
            hts_description=str(match.get("description") or ""),
            general_rate=str(match.get("general") or "Unknown"),
            special_rates=str(match.get("special") or ""),
            column2_rate=str(match.get("other") or "Unknown"),  # USITC calls Column 2 "other"
        )

    # ------------------------------------------------------------------
    # Existing chunk analyzer (unchanged logic)
    # ------------------------------------------------------------------

    async def _process_chunk(self, event: dict, chunk: list[dict], idx: int) -> list[dict]:
        prompt = (
            f"Tariff Event:\n{json.dumps(event, indent=2)}\n\n"
            f"BOM Chunk {idx + 1} ({len(chunk)} SKUs):\n{json.dumps(chunk, indent=2)}"
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = _extract_text(response)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            result = json.loads(text)
            return result if isinstance(result, list) else []
        except Exception:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
        return []

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log_agent_run(self, entry: dict) -> None:
        _AGENT_RUNS_LOG.parent.mkdir(exist_ok=True)
        record = {"logged_at": datetime.now(timezone.utc).isoformat(), **entry}
        with _AGENT_RUNS_LOG.open("a") as f:
            f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_text(response) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def _parse_json(text: str) -> dict | None:
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


def _normalize_hts_code(raw: str) -> str:
    """Convert zero-padded codes like '8542310000' to dotted '8542.31'.

    The Census API returns 10-digit codes; the USITC API expects 4-6 digit
    dotted notation for reliable matches.
    """
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) >= 6:
        # Standard 4.2 dotted format (e.g. 8542.31)
        return f"{digits[:4]}.{digits[4:6]}"
    return raw
