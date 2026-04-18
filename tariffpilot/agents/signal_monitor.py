"""Signal Monitor Agent — ReAct loop with Brave Search tool."""

import json
import asyncio
import anthropic
from tools.mcp_client import BraveMCPClient

MODEL = "claude-sonnet-4-6"

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
    "name": "brave_search",
    "description": "Search the web for current tariff and trade policy information. Returns recent news and official government announcements.",
    "input_schema": {
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
}


class SignalMonitorAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic()
        self.brave = BraveMCPClient()
        self.max_search_rounds = 3

    async def run(self, raw_event: dict) -> dict:
        print(f"\n[SignalMonitor] Starting ReAct loop for event: {raw_event.get('event_id', 'unknown')}")
        messages = [
            {
                "role": "user",
                "content": f"Enrich this tariff event signal:\n{json.dumps(raw_event, indent=2)}",
            }
        ]

        search_rounds = 0
        final_result = None

        while search_rounds < self.max_search_rounds:
            response = await self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[BRAVE_TOOL_DEF],
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                text = self._extract_text(response)
                final_result = self._parse_json(text)
                if final_result:
                    final_result["search_rounds_used"] = search_rounds
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                has_search = False

                for block in response.content:
                    if block.type == "tool_use" and block.name == "brave_search":
                        has_search = True
                        search_rounds += 1
                        query = block.input.get("query", "")
                        count = block.input.get("count", 5)
                        print(f"[SignalMonitor] Round {search_rounds}: searching → {query!r}")
                        results = await self._execute_brave_search(query, count)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(results),
                        })

                if not has_search:
                    text = self._extract_text(response)
                    final_result = self._parse_json(text)
                    if final_result:
                        final_result["search_rounds_used"] = search_rounds
                    break

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                confidence = self._check_confidence(response)
                if confidence >= 0.85:
                    final_result_response = await self.client.messages.create(
                        model=MODEL,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        tools=[BRAVE_TOOL_DEF],
                        messages=messages + [
                            {"role": "user", "content": "Confidence is sufficient. Return the final enriched JSON now."}
                        ],
                    )
                    text = self._extract_text(final_result_response)
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

    async def _execute_brave_search(self, query: str, count: int) -> list[dict]:
        return await self.brave.search(query, count)

    def _extract_text(self, response) -> str:
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    def _parse_json(self, text: str) -> dict | None:
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

    def _check_confidence(self, response) -> float:
        text = self._extract_text(response)
        if "confidence" in text.lower():
            import re
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
