from __future__ import annotations
"""BOM Mapper Agent — cross-references enriched tariff event against company BOM."""

import json
import asyncio
from groq import AsyncGroq
from utils.context_builder import compile_business_context

MODEL = "llama-3.3-70b-versatile"
CHUNK_SIZE = 50

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
        self.client = AsyncGroq()

    async def run(self, enriched_event: dict, bom: list[dict], user_id: str = "") -> dict:
        print(f"\n[BOMMapper] Mapping {len(bom)} SKUs against tariff event")
        self._biz_context = compile_business_context(user_id) if user_id else ""
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

    async def _process_chunk(self, event: dict, chunk: list[dict], idx: int) -> list[dict]:
        prompt = (
            f"Tariff Event:\n{json.dumps(event, indent=2)}\n\n"
            f"BOM Chunk {idx + 1} ({len(chunk)} SKUs):\n{json.dumps(chunk, indent=2)}"
        )

        response = await self.client.chat.completions.create(
            model=MODEL,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": f"{self._biz_context}\n\n{SYSTEM_PROMPT}".strip() if getattr(self, '_biz_context', '') else SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        text = response.choices[0].message.content or ""

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
