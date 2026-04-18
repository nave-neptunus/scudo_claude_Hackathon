"""BOM Mapper Agent — HS code cross-reference against BOM (Groq via OpenAI SDK)."""

import os
import json
import asyncio
from openai import AsyncOpenAI

MODEL = "llama-3.3-70b-versatile"
CHUNK_SIZE = 50

SYSTEM_PROMPT = """<instructions>
You are a supply chain cost analyst. Given a tariff event and BOM SKUs,
identify which SKUs are affected and calculate the financial impact.
</instructions>
<context>
Match HS codes at 8-digit, 6-digit, 4-digit, and 2-digit parent levels (cascade match).
Only flag SKUs whose supplier_country is in the tariff's affected_countries AND
whose hs_code matches the tariff hs_codes at any precision level.
</context>
<task>
For each affected SKU:
  annual_tariff_impact_usd = annual_spend_usd * (rate_delta_pct / 100)
Severity: CRITICAL > $500k, HIGH > $100k, MEDIUM > $10k, LOW otherwise
</task>
<output_format>
Return ONLY valid JSON array. Each element:
{
  "sku": "string", "description": "string", "hs_code": "string",
  "supplier": "string", "supplier_country": "string",
  "annual_spend_usd": 0.0, "annual_tariff_impact_usd": 0.0,
  "severity": "CRITICAL", "match_level": "8-digit",
  "has_domestic_alt": true, "alt_supplier": "string or null",
  "lead_time_weeks": 0, "critical_path": true
}
No markdown. Return ONLY the JSON array (may be empty []).
</output_format>"""


class BOMMapperAgent:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        )

    async def run(self, enriched_event: dict, bom: list[dict]) -> dict:
        print(f"\n[BOMMapper] Mapping {len(bom)} SKUs against tariff event")
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
        print(f"[BOMMapper] Found {len(affected)} affected SKUs, total impact: ${total_impact:,.0f}/yr")

        return {
            "affected_skus": affected,
            "total_annual_tariff_impact_usd": total_impact,
            "affected_sku_count": len(affected),
            "total_sku_count": len(bom),
            "severity_breakdown": {
                "CRITICAL": sum(1 for s in affected if s.get("severity") == "CRITICAL"),
                "HIGH": sum(1 for s in affected if s.get("severity") == "HIGH"),
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
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            result = json.loads(text)
            return result if isinstance(result, list) else []
        except Exception:
            start, end = text.find("["), text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
        return []
