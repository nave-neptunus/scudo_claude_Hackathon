"""Signal Monitor Agent — manual ReAct loop (no tool-calling API, works on any model)."""

import os
import re
import json
import asyncio
from openai import AsyncOpenAI
from tools.mcp_client import BraveMCPClient

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """<instructions>
You are a trade intelligence analyst. Enrich tariff event signals using a ReAct loop.
Each round you may request up to 2 searches. After receiving results, reason over them.
Stop searching when you have enough confidence (>= 0.85) or after 3 rounds.
</instructions>

<context>
Focus on official sources (USTR, Commerce, CBP, WTO) and trade publications.
</context>

<react_format>
When you need to search, respond ONLY with this exact format (one search per line):
SEARCH: your search query here
SEARCH: optional second query here

When you have enough information, respond with ONLY the final JSON (no SEARCH: lines).
</react_format>

<output_format>
Final JSON structure (return ONLY this when done searching):
{
  "event_id": "string",
  "description": "string",
  "hs_codes": ["8542.31.00"],
  "old_rate_pct": 0.0,
  "new_rate_pct": 84.0,
  "rate_delta_pct": 84.0,
  "affected_countries": ["China"],
  "effective_date": "2026-05-01",
  "threat_level": "CRITICAL",
  "confidence_score": 0.92,
  "search_rounds_used": 2,
  "key_facts": ["fact1"],
  "sources": ["url1"]
}
No markdown, no code fences. Return ONLY the JSON object.
</output_format>"""


class SignalMonitorAgent:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        )
        self.brave = BraveMCPClient()
        self.max_search_rounds = 3

    async def run(self, raw_event: dict) -> dict:
        print(f"\n[SignalMonitor] Starting ReAct loop for event: {raw_event.get('event_id', 'unknown')}")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Enrich this tariff event signal:\n{json.dumps(raw_event, indent=2)}"},
        ]
        search_rounds = 0
        final_result = None

        while search_rounds <= self.max_search_rounds:
            response = await self.client.chat.completions.create(
                model=MODEL, messages=messages, max_tokens=1024,
            )
            text = (response.choices[0].message.content or "").strip()
            messages.append({"role": "assistant", "content": text})

            # Check if model wants to search
            queries = re.findall(r"^SEARCH:\s*(.+)$", text, re.MULTILINE)

            if not queries:
                # No more searches — parse as final JSON
                final_result = self._parse_json(text)
                if final_result:
                    final_result["search_rounds_used"] = search_rounds
                break

            # Execute searches and collect results
            search_rounds += 1
            all_results = []
            for query in queries[:2]:
                query = query.strip()
                print(f"[SignalMonitor] Round {search_rounds}: searching → {query!r}")
                results = await self.brave.search(query, 4)
                all_results.extend(results)

            messages.append({
                "role": "user",
                "content": (
                    f"Search results (round {search_rounds}):\n{json.dumps(all_results, indent=2)}\n\n"
                    + ("Now return the final enriched JSON." if search_rounds >= self.max_search_rounds
                       else "Continue reasoning. If you need more searches use SEARCH: lines, otherwise return the JSON.")
                ),
            })

        if not final_result:
            final_result = self._fallback(raw_event, search_rounds)

        print(f"[SignalMonitor] Done. Confidence: {final_result.get('confidence_score', 0):.2f}, rounds: {final_result.get('search_rounds_used', 0)}")
        return final_result

    def _parse_json(self, text: str) -> dict | None:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except Exception:
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
        return None

    def _fallback(self, raw_event: dict, search_rounds: int) -> dict:
        hints = raw_event.get("hs_codes_hint", [])
        countries = raw_event.get("affected_countries_hint", ["China"])
        rate_hint = raw_event.get("rate_change_hint", "0% → 25%")
        old_r, new_r = 0.0, 25.0
        try:
            parts = rate_hint.replace("%", "").split("→")
            old_r, new_r = float(parts[0].strip()), float(parts[1].strip())
        except Exception:
            pass
        return {
            "event_id": raw_event.get("event_id", "UNKNOWN"),
            "description": raw_event.get("description", "Unknown tariff event"),
            "hs_codes": hints or ["8542.31.00"],
            "old_rate_pct": old_r, "new_rate_pct": new_r,
            "rate_delta_pct": new_r - old_r,
            "affected_countries": countries,
            "effective_date": raw_event.get("effective_date_hint", "2026-05-01"),
            "threat_level": "HIGH" if (new_r - old_r) >= 25 else "MEDIUM",
            "confidence_score": 0.55,
            "search_rounds_used": search_rounds,
            "key_facts": ["Fallback enrichment — search rounds exhausted"],
            "sources": [],
        }
