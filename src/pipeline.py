from __future__ import annotations
"""API-mode pipeline: runs agents, streams progress, returns awaiting_approval."""

import json
import asyncio
import tempfile
import traceback
from datetime import datetime, timezone

from groq import AsyncGroq
from agents.signal_monitor import SignalMonitorAgent
from agents.bom_mapper import BOMMapperAgent
from agents.scenario_modeler import run_parallel_scenarios
from agents.hitl_gate import HITLGateAgent
from db.supabase_store import store

MODEL_PLANNER = "llama-3.3-70b-versatile"
MODEL_BUILDER = "llama-3.3-70b-versatile"

SYNTHESIZE_SYSTEM = """<instructions>
You are a supply chain strategy synthesizer. Rank 3 parallel scenario analyses.
Consider: cost impact (lower is better), lead time (lower is better), risk (lower is better),
supplier_coverage_pct (higher is better). Weight cost and risk equally.
</instructions>
<task>
Rank the 3 scenarios from best (rank=1) to worst (rank=3).
Add "rank" (int) and "recommendation_rationale" (str, 1-2 sentences) to each.
Return all 3 with rank added.
</task>
<output_format>
Return ONLY valid JSON array. No markdown.
</output_format>"""


def _progress(rec_id: str, stage: str, status: str, detail: str = ""):
    store.push_progress(rec_id, {
        "stage": stage,
        "status": status,
        "detail": detail,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


async def _synthesize(scenarios: list[dict]) -> list[dict]:
    client = AsyncGroq()
    response = await client.chat.completions.create(
        model=MODEL_PLANNER,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": SYNTHESIZE_SYSTEM},
            {"role": "user", "content": json.dumps(scenarios, indent=2)}
        ],
    )
    text = response.choices[0].message.content or "[]"
    text = text.strip()
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
        s["recommendation_rationale"] = "Ranking unavailable."
    return scenarios


async def _draft_emails(enriched_event: dict, bom_analysis: dict, chosen_scenario: dict) -> list[dict]:
    """Draft supplier emails for the chosen scenario without sending. Opus reviewer pass included."""
    client = AsyncGroq()

    # Builder: draft emails
    draft_prompt = f"""Tariff event: {json.dumps(enriched_event, indent=2)}

BOM exposure: {json.dumps(bom_analysis.get('summary', {}), indent=2)}

Chosen scenario: {json.dumps(chosen_scenario, indent=2)}

Draft supplier notification emails for the top affected SKUs in the chosen scenario."""

    system_prompt = HITLGateAgent(demo_mode=True).EMAIL_SYSTEM if hasattr(HITLGateAgent, "EMAIL_SYSTEM") else _EMAIL_SYSTEM
    response = await client.chat.completions.create(
        model=MODEL_BUILDER,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": draft_prompt}
        ],
    )
    text = response.choices[0].message.content or "[]"
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        emails = json.loads(text)
        if not isinstance(emails, list):
            emails = [emails]
    except Exception:
        emails = [{
            "to_supplier": "Supplier",
            "subject": f"Re: Supply chain re-routing — {enriched_event.get('event_id', '')}",
            "body": text,
            "sku_references": [],
            "priority": "HIGH",
        }]

    # Reviewer: opus-4-6 critiques draft
    review_prompt = f"""Review this draft supplier outreach email for:
1. Tone (professional, not alarmist)
2. Factual grounding (references specific SKUs and timelines)
3. Clear ask (action requested within 5 business days)
4. Missing fields

Email drafts: {json.dumps(emails, indent=2)}

Return ONLY valid JSON with same structure as input, improved where needed.
Add a "reviewer_notes" field to each email with a brief critique."""

    review_response = await client.chat.completions.create(
        model=MODEL_PLANNER,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": "You are a senior supply chain communications reviewer. Critique and improve supplier outreach emails for factual grounding, tone, and completeness. Return ONLY valid JSON array."},
            {"role": "user", "content": review_prompt}
        ],
    )
    review_text = review_response.choices[0].message.content or "[]"
    review_text = review_text.strip()
    if review_text.startswith("```"):
        lines = review_text.split("\n")
        review_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        reviewed = json.loads(review_text)
        if isinstance(reviewed, list) and reviewed:
            return reviewed
    except Exception:
        pass
    return emails


_EMAIL_SYSTEM = """<instructions>
You are a professional supply chain communications specialist. Draft supplier notification
emails based on the approved re-routing strategy. Be specific, professional, and action-oriented.
Include exact SKU references, timelines, and next steps.
</instructions>
<context>
These emails will go to real supplier contacts. Use formal business language.
Reference specific SKUs, volumes, and timelines. Make the ask clear and actionable.
Sign as "Supply Chain Team, [Company Name]".
</context>
<task>
Draft one email per unique supplier affected in the top_sku_actions of the chosen scenario.
Each email should: explain the strategic re-sourcing decision, reference specific SKUs,
state the desired qualification timeline, and request a response within 5 business days.
</task>
<output_format>
Return ONLY a valid JSON array of email objects:
[{"to_supplier": "Supplier Name", "subject": "...", "body": "...", "sku_references": ["SKU-001"], "priority": "HIGH"}]
No markdown. Return ONLY the JSON array.
</output_format>"""


async def run_pipeline(rec_id: str, event_id: str, bom_id: str, user_id: str = ""):
    """Full pipeline run for API mode. Stores result; no interactive prompts."""
    store.init_progress(rec_id)
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        raw_event = store.get_event(event_id)
        if not raw_event:
            raise ValueError(f"Event {event_id} not found")

        bom_rows = store.get_bom_rows(bom_id)
        if not bom_rows:
            raise ValueError(f"BOM {bom_id} has no rows")

        # Write BOM rows to temp file for agents that expect file path
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(bom_rows, f)
            bom_tmp = f.name

        # ── Stage 1: Signal Monitor ──────────────────────────────────────
        _progress(rec_id, "signal_monitor", "running", "Enriching tariff signal…")
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "signal_monitor", "model": MODEL_BUILDER,
            "input_payload": raw_event, "started_at": started_at,
        })
        enriched_event = await SignalMonitorAgent().run(raw_event, user_id=user_id)
        _progress(rec_id, "signal_monitor", "done",
                  f"Confidence {enriched_event.get('confidence_score', '?')} · {len(enriched_event.get('hs_codes', []))} HS codes")
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "signal_monitor", "model": MODEL_BUILDER,
            "output_payload": enriched_event, "ended_at": datetime.now(timezone.utc).isoformat(),
        })

        # ── Stage 2: BOM Mapper ─────────────────────────────────────────
        _progress(rec_id, "bom_mapper", "running", "Mapping SKUs to HS codes…")
        bom_analysis = await BOMMapperAgent().run(enriched_event, bom_rows, user_id=user_id)
        affected = len(bom_analysis.get("affected_skus", bom_analysis.get("sku_impacts", [])))
        exposure = bom_analysis.get("total_annual_tariff_impact_usd", 0)
        _progress(rec_id, "bom_mapper", "done",
                  f"{affected} SKUs affected · ${exposure:,.0f}/yr exposure")
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "bom_mapper", "model": MODEL_BUILDER,
            "output_payload": {"affected": affected, "exposure_usd": exposure},
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })

        # ── Stage 3: Parallel Scenario Modeler ─────────────────────────
        _progress(rec_id, "scenario_modeler", "running", "Running 3 sub-agents in parallel…")
        scenarios = await run_parallel_scenarios(enriched_event, bom_analysis, user_id=user_id)
        _progress(rec_id, "scenario_modeler", "done", f"{len(scenarios)} scenarios ready")

        # ── Synthesize + Rank (Planner — opus-4-6) ─────────────────────
        _progress(rec_id, "synthesizer", "running", "Ranking scenarios…")
        ranked = await _synthesize(scenarios)
        _progress(rec_id, "synthesizer", "done",
                  f"Top pick: {ranked[0].get('strategy', ranked[0].get('scenario_type', '?'))} (rank 1)")

        # ── Stage 4: Draft emails — HITL awaiting approval ──────────────
        _progress(rec_id, "hitl_gate", "running", "Drafting supplier emails…")
        top_scenario = ranked[0]
        emails = await _draft_emails(enriched_event, bom_analysis, top_scenario)
        _progress(rec_id, "hitl_gate", "awaiting_approval",
                  "Emails drafted · awaiting operator authorization")

        store.update_recommendation(rec_id, {
            "status": "awaiting_approval",
            "enriched_event": enriched_event,
            "bom_analysis": bom_analysis,
            "ranked_scenarios": ranked,
            "draft_email": {
                "to": emails[0].get("to_supplier") if emails else None,
                "subject": emails[0].get("subject", "") if emails else "",
                "body": emails[0].get("body", "") if emails else "",
                "scenario_ref": top_scenario.get("strategy", ""),
                "all_emails": emails,
            },
        })
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "hitl_gate", "model": MODEL_PLANNER,
            "output_payload": {"emails_drafted": len(emails), "status": "awaiting_approval"},
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        tb = traceback.format_exc()
        _progress(rec_id, "pipeline", "error", str(exc))
        store.update_recommendation(rec_id, {
            "status": "error",
            "error": str(exc),
            "traceback": tb,
        })
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "pipeline", "model": MODEL_BUILDER,
            "output_payload": {"error": str(exc)},
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })
