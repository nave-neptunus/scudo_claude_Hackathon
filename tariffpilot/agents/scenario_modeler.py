"""Scenario Modeler — 3 isolated instances run in parallel (Groq via OpenAI SDK)."""

import os
import json
import asyncio
import time
from openai import AsyncOpenAI

MODEL = "llama-3.3-70b-versatile"

SCENARIO_SYSTEMS = {
    "reshore": """<instructions>
You are a domestic manufacturing strategist. Model ONLY the RESHORE scenario:
moving all affected supply to US-based suppliers.
</instructions>
<context>
US labor premium: 2.3× China. CHIPS Act: 25% tax credit. Qualification: 12-18 months.
Domestic coverage: 60-75% electronics, 85% mechanical. No tariff once reshored.
</context>
<task>Analyze affected SKUs (has_domestic_alt=true). Calculate cost delta from labor premium
offset by eliminated tariffs. Be specific with numbers.</task>
<output_format>
Return ONLY valid JSON:
{"strategy":"reshore","annual_cost_delta_usd":0.0,"lead_time_months":0,
"supplier_coverage_pct":0.0,"risk_score":0.0,"confidence":0.0,
"top_sku_actions":[{"sku":"string","action":"string","new_supplier":"string","cost_delta_usd":0.0}],
"pros":["string"],"cons":["string"],"summary":"2-3 sentences"}
No markdown. Return ONLY JSON.
</output_format>""",

    "nearshore": """<instructions>
You are a USMCA trade specialist. Model ONLY the NEARSHORE scenario via Mexico/Canada.
</instructions>
<context>
USMCA RVC: 75% electronics. Mexico labor: $4.50/hr (40% premium vs China).
Qualification: 8-14 months. Logistics overhead: +$0.50-1.20/unit.
</context>
<task>Prioritize Mexico maquiladoras. Calculate total cost including logistics and qualification.</task>
<output_format>
Return ONLY valid JSON:
{"strategy":"nearshore","annual_cost_delta_usd":0.0,"lead_time_months":0,
"supplier_coverage_pct":0.0,"risk_score":0.0,"confidence":0.0,
"top_sku_actions":[{"sku":"string","action":"string","new_supplier":"string","cost_delta_usd":0.0}],
"pros":["string"],"cons":["string"],"summary":"2-3 sentences"}
No markdown. Return ONLY JSON.
</output_format>""",

    "dual_source": """<instructions>
You are a supply chain risk strategist. Model ONLY the DUAL-SOURCE scenario:
split supply between China and tariff-exempt alternatives.
</instructions>
<context>
Optimal split: 60/40 or 70/30 (exempt/China). Safety stock: +15-20%.
Overhead: +8-12% management cost. Price improvement: 5-8%. Qualification: 6-10 months.
</context>
<task>Model optimal split per SKU. Calculate partial tariff elimination vs overhead.</task>
<output_format>
Return ONLY valid JSON:
{"strategy":"dual_source","annual_cost_delta_usd":0.0,"lead_time_months":0,
"supplier_coverage_pct":0.0,"risk_score":0.0,"confidence":0.0,
"split_ratio":{"exempt_pct":65,"china_pct":35},
"top_sku_actions":[{"sku":"string","action":"string","new_supplier":"string","cost_delta_usd":0.0}],
"pros":["string"],"cons":["string"],"summary":"2-3 sentences"}
No markdown. Return ONLY JSON.
</output_format>""",
}


class ScenarioModelerAgent:
    def __init__(self, strategy: str):
        assert strategy in SCENARIO_SYSTEMS
        self.strategy = strategy
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        )

    async def run(self, enriched_event: dict, bom_analysis: dict) -> dict:
        prompt = (
            f"Tariff Event:\n{json.dumps(enriched_event, indent=2)}\n\n"
            f"BOM Analysis:\n{json.dumps(bom_analysis, indent=2)}"
        )
        response = await self.client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SCENARIO_SYSTEMS[self.strategy]},
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
            result["strategy"] = self.strategy
            return result
        except Exception:
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    result = json.loads(text[start:end])
                    result["strategy"] = self.strategy
                    return result
                except Exception:
                    pass
        return {
            "strategy": self.strategy, "annual_cost_delta_usd": 0.0,
            "lead_time_months": 12, "supplier_coverage_pct": 0.0,
            "risk_score": 0.5, "confidence": 0.0,
            "top_sku_actions": [], "pros": [], "cons": ["Parse error"],
            "summary": "Parse error.",
        }


async def _run_with_retry(agent: "ScenarioModelerAgent", enriched_event: dict, bom_analysis: dict, delay: float) -> dict:
    """Stagger launch by delay seconds, then retry once on 429."""
    await asyncio.sleep(delay)
    try:
        return await agent.run(enriched_event, bom_analysis)
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            print(f"[ScenarioModeler] {agent.strategy} rate-limited, retrying in 30s...")
            await asyncio.sleep(30)
            return await agent.run(enriched_event, bom_analysis)
        raise


async def run_parallel_scenarios(enriched_event: dict, bom_analysis: dict) -> list[dict]:
    agents = [ScenarioModelerAgent(s) for s in ("reshore", "nearshore", "dual_source")]
    t0 = time.time()
    print(f"\n[ScenarioModeler] Spawning 3 parallel scenario agents at t=0.000s")

    # Stagger by 2s each to stay under TPM limits on free tier
    results = await asyncio.gather(
        *[_run_with_retry(a, enriched_event, bom_analysis, i * 2.0) for i, a in enumerate(agents)],
        return_exceptions=True,
    )

    scenarios = []
    for i, result in enumerate(results):
        elapsed = time.time() - t0
        strategy = ("reshore", "nearshore", "dual_source")[i]
        if isinstance(result, Exception):
            print(f"[ScenarioModeler] {strategy} FAILED at t={elapsed:.3f}s: {result}")
            scenarios.append({"strategy": strategy, "error": str(result), "confidence": 0.0})
        else:
            print(f"[ScenarioModeler] {strategy} done   at t={elapsed:.3f}s, delta=${result.get('annual_cost_delta_usd', 0):,.0f}")
            scenarios.append(result)
    return scenarios
