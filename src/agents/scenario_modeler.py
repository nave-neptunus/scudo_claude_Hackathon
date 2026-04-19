from __future__ import annotations
"""Scenario Modeler Agent — 3 isolated instances run in parallel via asyncio.gather()."""

import json
import asyncio
from groq import AsyncGroq
from utils.context_builder import compile_business_context

MODEL = "llama-3.3-70b-versatile"

SCENARIO_SYSTEMS = {
    "reshore": """<instructions>
You are a domestic manufacturing strategist. Your ONLY job is to model the RESHORE scenario:
moving all affected supply to US-based suppliers. You think exclusively in terms of domestic
labor costs, CHIPS Act incentives, and US supplier qualification timelines.
</instructions>

<context>
Reshore assumptions:
- US labor premium: 2.3× vs current China costs
- CHIPS Act qualification: eligible components may receive 25% investment tax credit
- Supplier qualification timeline: 12-18 months minimum for critical components
- Domestic supplier coverage: ~60-75% for electronics, ~85% for mechanical parts
- No tariff exposure once reshored (0% rate delta)
</context>

<task>
Analyze the affected SKUs and calculate the reshore scenario financials.
Focus on: which SKUs CAN be reshored (has_domestic_alt=true), cost delta from labor premium,
offset from eliminated tariff exposure, and realistic timeline.
</task>

<output_format>
Return ONLY valid JSON:
{
  "strategy": "reshore",
  "annual_cost_delta_usd": 0.0,
  "lead_time_months": 0,
  "supplier_coverage_pct": 0.0,
  "risk_score": 0.0,
  "confidence": 0.0,
  "top_sku_actions": [{"sku": "string", "action": "string", "new_supplier": "string", "cost_delta_usd": 0.0}],
  "pros": ["string"],
  "cons": ["string"],
  "summary": "string (2-3 sentences)"
}
No markdown. Return ONLY JSON.
</output_format>""",

    "nearshore": """<instructions>
You are a USMCA trade specialist. Your ONLY job is to model the NEARSHORE scenario:
routing affected supply through Mexico and Canada under USMCA to eliminate tariff exposure.
You think exclusively in terms of USMCA rules of origin, maquiladora economics, and
Mexico/Canada supplier networks.
</instructions>

<context>
Nearshore assumptions:
- USMCA regional value content requirement: 75% for electronics, 62.5% for autos
- Mexico labor rate: ~$4.50/hr vs China $3.20/hr (40% premium, much less than US)
- Canada labor rate: ~$28/hr (comparable to US but USMCA-exempt)
- Supplier qualification: 8-14 months for Mexico suppliers
- Existing maquiladora networks in Tijuana, Monterrey, Ciudad Juárez
- Logistics cost: +$0.50-1.20/unit for cross-border vs China direct
</context>

<task>
Analyze affected SKUs for nearshore viability. Prioritize Mexico maquiladoras for
cost-sensitive high-volume parts. Flag SKUs where no USMCA supplier exists.
Calculate total cost impact including logistics and qualification overhead.
</task>

<output_format>
Return ONLY valid JSON:
{
  "strategy": "nearshore",
  "annual_cost_delta_usd": 0.0,
  "lead_time_months": 0,
  "supplier_coverage_pct": 0.0,
  "risk_score": 0.0,
  "confidence": 0.0,
  "top_sku_actions": [{"sku": "string", "action": "string", "new_supplier": "string", "cost_delta_usd": 0.0}],
  "pros": ["string"],
  "cons": ["string"],
  "summary": "string (2-3 sentences)"
}
No markdown. Return ONLY JSON.
</output_format>""",

    "dual_source": """<instructions>
You are a supply chain risk strategist. Your ONLY job is to model the DUAL-SOURCE scenario:
splitting supply between current China sources and tariff-exempt alternatives to balance
cost and risk. You think exclusively in terms of optimal split ratios, safety stock,
and portfolio risk reduction.
</instructions>

<context>
Dual-source assumptions:
- Optimal split: 60/40 or 70/30 (tariff-exempt / China) based on tariff sensitivity
- Safety stock increase: +15-20% to buffer supplier switching delays
- Overhead: +8-12% supplier management cost for running dual supply chains
- Price negotiation: dual-source typically yields 5-8% better pricing from each supplier
- Tariff exposure reduced by percentage shifted to exempt sources
- Qualification timeline: 6-10 months (faster than full reshore/nearshore)
</context>

<task>
Model the optimal dual-source split for each affected SKU. Calculate partial tariff
elimination benefit vs overhead cost. Determine which SKUs should stay China-dominant
(low tariff sensitivity) vs which should shift to 70% exempt sourcing.
</task>

<output_format>
Return ONLY valid JSON:
{
  "strategy": "dual_source",
  "annual_cost_delta_usd": 0.0,
  "lead_time_months": 0,
  "supplier_coverage_pct": 0.0,
  "risk_score": 0.0,
  "confidence": 0.0,
  "split_ratio": {"exempt_pct": 65, "china_pct": 35},
  "top_sku_actions": [{"sku": "string", "action": "string", "new_supplier": "string", "cost_delta_usd": 0.0}],
  "pros": ["string"],
  "cons": ["string"],
  "summary": "string (2-3 sentences)"
}
No markdown. Return ONLY JSON.
</output_format>""",
}


class ScenarioModelerAgent:
    def __init__(self, strategy: str):
        assert strategy in SCENARIO_SYSTEMS, f"Unknown strategy: {strategy}"
        self.strategy = strategy
        self.client = AsyncGroq()

    async def run(self, enriched_event: dict, bom_analysis: dict, user_id: str = "") -> dict:
        prompt = (
            f"Tariff Event:\n{json.dumps(enriched_event, indent=2)}\n\n"
            f"BOM Analysis:\n{json.dumps(bom_analysis, indent=2)}"
        )
        biz = compile_business_context(user_id) if user_id else ""
        system = f"{biz}\n\n{SCENARIO_SYSTEMS[self.strategy]}".strip() if biz else SCENARIO_SYSTEMS[self.strategy]

        response = await self.client.chat.completions.create(
            model=MODEL,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
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
            result["strategy"] = self.strategy
            return result
        except Exception:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    result = json.loads(text[start:end])
                    result["strategy"] = self.strategy
                    return result
                except Exception:
                    pass

        return {
            "strategy": self.strategy,
            "annual_cost_delta_usd": 0.0,
            "lead_time_months": 12,
            "supplier_coverage_pct": 0.0,
            "risk_score": 0.5,
            "confidence": 0.0,
            "top_sku_actions": [],
            "pros": [],
            "cons": ["Parse error — raw response unavailable"],
            "summary": f"Could not parse {self.strategy} scenario response.",
        }


async def run_parallel_scenarios(enriched_event: dict, bom_analysis: dict, user_id: str = "") -> list[dict]:
    """Run all 3 scenario agents simultaneously — core parallelism demo moment."""
    import time
    agents = [
        ScenarioModelerAgent("reshore"),
        ScenarioModelerAgent("nearshore"),
        ScenarioModelerAgent("dual_source"),
    ]

    t0 = time.time()
    print(f"\n[ScenarioModeler] Spawning 3 parallel scenario agents at t=0.000s")

    results = await asyncio.gather(
        *[agent.run(enriched_event, bom_analysis, user_id) for agent in agents],
        return_exceptions=True,
    )

    scenarios = []
    for i, result in enumerate(results):
        elapsed = time.time() - t0
        strategy = ["reshore", "nearshore", "dual_source"][i]
        if isinstance(result, Exception):
            print(f"[ScenarioModeler] {strategy} failed at t={elapsed:.3f}s: {result}")
            scenarios.append({"strategy": strategy, "error": str(result), "confidence": 0.0})
        else:
            print(f"[ScenarioModeler] {strategy} complete at t={elapsed:.3f}s, cost_delta=${result.get('annual_cost_delta_usd', 0):,.0f}")
            scenarios.append(result)

    return scenarios
