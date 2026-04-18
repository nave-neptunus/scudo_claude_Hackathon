"""Orchestrator Agent — Layer 1 manager. Runs the full TariffPilot pipeline."""

import json
import asyncio
import anthropic
from datetime import datetime
from pathlib import Path

from agents.signal_monitor import SignalMonitorAgent
from agents.bom_mapper import BOMMapperAgent
from agents.scenario_modeler import run_parallel_scenarios
from agents.hitl_gate import HITLGateAgent
from data.bom_loader import load_bom

MODEL = "claude-sonnet-4-6"
OUTPUT_DIR = Path("output")

SYNTHESIZE_SYSTEM = """<instructions>
You are a supply chain strategy synthesizer. Given 3 parallel scenario analyses,
rank them and produce a recommendation. Consider: cost impact, lead time, risk, and
supplier coverage. Weight cost and risk equally.
</instructions>

<context>
You receive 3 scenarios: reshore, nearshore, dual_source.
Each has: annual_cost_delta_usd, lead_time_months, supplier_coverage_pct, risk_score, confidence.
A lower annual_cost_delta_usd is better (negative = savings).
A lower risk_score is better (0.0 = no risk, 1.0 = maximum risk).
Higher supplier_coverage_pct is better.
</context>

<task>
Rank the 3 scenarios from best to worst for immediate implementation.
Add a "rank" field (1=best) and "recommendation_rationale" to each.
Return all 3 scenarios, ranked.
</task>

<output_format>
Return ONLY valid JSON array (same structure as input, with rank and recommendation_rationale added).
No markdown. Return ONLY the JSON array.
</output_format>"""


class OrchestratorAgent:
    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.client = anthropic.AsyncAnthropic()
        self.audit_trail = []
        OUTPUT_DIR.mkdir(exist_ok=True)

    async def run(self, raw_event: dict, bom_path: str | None = None) -> dict:
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        print(f"\n{'=' * 70}")
        print(f"  TARIFFPILOT PIPELINE — Run ID: {run_id}")
        print(f"  Event: {raw_event.get('event_id', 'unknown')}")
        print(f"{'=' * 70}\n")

        bom = load_bom(bom_path)
        print(f"[Orchestrator] Loaded BOM: {len(bom)} SKUs")

        # Stage 1: Signal Monitor
        enriched_event = await self._run_stage(
            "SignalMonitor",
            SignalMonitorAgent().run(raw_event),
        )

        # Stage 2: BOM Mapper
        bom_analysis = await self._run_stage(
            "BOMMapper",
            BOMMapperAgent().run(enriched_event, bom),
        )

        # Stage 3: Parallel Scenario Modelers
        scenarios = await self._run_stage(
            "ScenarioModeler[3× parallel]",
            run_parallel_scenarios(enriched_event, bom_analysis),
        )

        # Synthesize + rank scenarios
        ranked_scenarios = await self._synthesize(scenarios)

        # Stage 4: HITL Gate
        hitl = HITLGateAgent(demo_mode=self.demo_mode)
        package = await self._run_stage(
            "HITLGate",
            hitl.run(enriched_event, bom_analysis, scenarios, ranked_scenarios),
        )

        result = {
            "run_id": run_id,
            "raw_event": raw_event,
            "enriched_event": enriched_event,
            "bom_analysis": bom_analysis,
            "scenarios": scenarios,
            "ranked_scenarios": ranked_scenarios,
            "package": package,
            "audit_trail": self.audit_trail,
            "completed_at": datetime.utcnow().isoformat(),
        }

        self._write_audit(result, run_id)

        status = package.get("status", "UNKNOWN")
        print(f"\n{'=' * 70}")
        print(f"  PIPELINE COMPLETE — Status: {status}")
        print(f"  Audit trail: output/tariffpilot_result_{run_id}.json")
        print(f"{'=' * 70}\n")

        return result

    async def _run_stage(self, name: str, coro, retries: int = 1):
        started_at = datetime.utcnow().isoformat()
        print(f"\n[Orchestrator] ▶ Starting {name}  ({started_at})")

        for attempt in range(retries + 1):
            try:
                result = await coro
                completed_at = datetime.utcnow().isoformat()
                self.audit_trail.append({
                    "stage": name,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "attempt": attempt + 1,
                    "status": "SUCCESS",
                })
                print(f"[Orchestrator] ✓ {name} complete")
                return result
            except Exception as e:
                if attempt < retries:
                    print(f"[Orchestrator] ✗ {name} failed (attempt {attempt+1}), retrying: {e}")
                    await asyncio.sleep(2)
                else:
                    self.audit_trail.append({
                        "stage": name,
                        "started_at": started_at,
                        "completed_at": datetime.utcnow().isoformat(),
                        "attempt": attempt + 1,
                        "status": "FAILED",
                        "error": str(e),
                    })
                    raise

    async def _synthesize(self, scenarios: list[dict]) -> list[dict]:
        print(f"\n[Orchestrator] Synthesizing and ranking {len(scenarios)} scenarios...")

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYNTHESIZE_SYSTEM,
            messages=[
                {"role": "user", "content": json.dumps(scenarios, indent=2)}
            ],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            ranked = json.loads(text)
            if isinstance(ranked, list):
                ranked.sort(key=lambda x: x.get("rank", 99))
                return ranked
        except Exception:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    ranked = json.loads(text[start:end])
                    ranked.sort(key=lambda x: x.get("rank", 99))
                    return ranked
                except Exception:
                    pass

        for i, s in enumerate(scenarios):
            s["rank"] = i + 1
            s["recommendation_rationale"] = "Ranking unavailable — parse error"
        return scenarios

    def _write_audit(self, result: dict, run_id: str):
        path = OUTPUT_DIR / f"tariffpilot_result_{run_id}.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)
