"""Orchestrator Agent — runs the full TariffPilot pipeline (Groq via OpenAI SDK)."""

import os
import json
import asyncio
from openai import AsyncOpenAI
from datetime import datetime
from pathlib import Path

from agents.signal_monitor import SignalMonitorAgent
from agents.bom_mapper import BOMMapperAgent
from agents.scenario_modeler import run_parallel_scenarios
from agents.hitl_gate import HITLGateAgent
from data.bom_loader import load_bom

MODEL = "llama-3.3-70b-versatile"
OUTPUT_DIR = Path("output")

SYNTHESIZE_SYSTEM = """<instructions>
You are a supply chain strategy synthesizer. Rank 3 scenario analyses best-to-worst.
Lower annual_cost_delta_usd is better (negative = savings). Lower risk_score is better.
Higher supplier_coverage_pct is better.
Add "rank" (1=best) and "recommendation_rationale" to each. Return all 3 sorted by rank.
</instructions>
<output_format>
Return ONLY valid JSON array with rank and recommendation_rationale added.
No markdown. Return ONLY the JSON array.
</output_format>"""


class OrchestratorAgent:
    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        )
        self.audit_trail = []
        OUTPUT_DIR.mkdir(exist_ok=True)

    async def run(self, raw_event: dict, bom_path: str | None = None) -> dict:
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        print(f"\n{'='*70}\n  TARIFFPILOT PIPELINE — Run ID: {run_id}")
        print(f"  Event: {raw_event.get('event_id','unknown')}\n{'='*70}\n")

        bom = load_bom(bom_path)
        print(f"[Orchestrator] Loaded BOM: {len(bom)} SKUs")

        enriched_event = await self._run_stage(
            "SignalMonitor", lambda: SignalMonitorAgent().run(raw_event)
        )
        bom_analysis = await self._run_stage(
            "BOMMapper", lambda: BOMMapperAgent().run(enriched_event, bom)
        )
        scenarios = await self._run_stage(
            "ScenarioModeler[3× parallel]",
            lambda: run_parallel_scenarios(enriched_event, bom_analysis)
        )
        ranked_scenarios = await self._synthesize(scenarios)

        package = await self._run_stage(
            "HITLGate",
            lambda: HITLGateAgent(demo_mode=self.demo_mode).run(
                enriched_event, bom_analysis, scenarios, ranked_scenarios
            )
        )

        result = {
            "run_id": run_id, "raw_event": raw_event,
            "enriched_event": enriched_event, "bom_analysis": bom_analysis,
            "scenarios": scenarios, "ranked_scenarios": ranked_scenarios,
            "package": package, "audit_trail": self.audit_trail,
            "completed_at": datetime.utcnow().isoformat(),
        }
        self._write_audit(result, run_id)

        status = package.get("status", "UNKNOWN")
        print(f"\n{'='*70}\n  PIPELINE COMPLETE — Status: {status}")
        print(f"  Audit trail: output/tariffpilot_result_{run_id}.json\n{'='*70}\n")
        return result

    async def _run_stage(self, name: str, factory, retries: int = 1):
        started_at = datetime.utcnow().isoformat()
        print(f"\n[Orchestrator] ▶ Starting {name}  ({started_at})")
        for attempt in range(retries + 1):
            try:
                result = await factory()
                self.audit_trail.append({"stage": name, "started_at": started_at,
                    "completed_at": datetime.utcnow().isoformat(),
                    "attempt": attempt + 1, "status": "SUCCESS"})
                print(f"[Orchestrator] ✓ {name} complete")
                return result
            except Exception as e:
                if attempt < retries:
                    print(f"[Orchestrator] ✗ {name} failed (attempt {attempt+1}), retrying: {e}")
                    await asyncio.sleep(2)
                else:
                    self.audit_trail.append({"stage": name, "started_at": started_at,
                        "completed_at": datetime.utcnow().isoformat(),
                        "attempt": attempt + 1, "status": "FAILED", "error": str(e)})
                    raise

    async def _synthesize(self, scenarios: list[dict]) -> list[dict]:
        print(f"\n[Orchestrator] Synthesizing and ranking {len(scenarios)} scenarios...")
        response = await self.client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYNTHESIZE_SYSTEM},
                {"role": "user", "content": json.dumps(scenarios, indent=2)},
            ],
            max_tokens=4096,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            ranked = json.loads(text)
            if isinstance(ranked, list):
                ranked.sort(key=lambda x: x.get("rank", 99))
                return ranked
        except Exception:
            start, end = text.find("["), text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    ranked = json.loads(text[start:end])
                    ranked.sort(key=lambda x: x.get("rank", 99))
                    return ranked
                except Exception:
                    pass
        for i, s in enumerate(scenarios):
            s["rank"] = i + 1
            s["recommendation_rationale"] = "Ranking unavailable"
        return scenarios

    def _write_audit(self, result: dict, run_id: str):
        path = OUTPUT_DIR / f"tariffpilot_result_{run_id}.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)
