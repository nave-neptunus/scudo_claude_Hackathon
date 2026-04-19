from __future__ import annotations
"""API-mode pipeline: runs agents, streams progress, returns awaiting_approval."""

import json
import asyncio
import tempfile
import time
import traceback
from datetime import datetime, timezone

from groq import AsyncGroq
from pydantic import ValidationError
from agents.signal_monitor import SignalMonitorAgent, EnrichedEvent
from agents.bom_mapper import BOMMapperAgent, BOMAnalysis
from agents.scenario_modeler import run_parallel_scenarios
from agents.hitl_gate import HITLGateAgent, EMAIL_SYSTEM as _EMAIL_SYSTEM
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
    bom_exposure = {
        "affected_skus": bom_analysis.get("affected_sku_count", 0),
        "total_annual_tariff_impact_usd": bom_analysis.get("total_annual_tariff_impact_usd", 0),
        "severity_breakdown": bom_analysis.get("severity_breakdown", {}),
    }
    draft_prompt = f"""Tariff event: {json.dumps(enriched_event, indent=2)}

BOM exposure: {json.dumps(bom_exposure, indent=2)}

Chosen scenario: {json.dumps(chosen_scenario, indent=2)}

Draft supplier notification emails for the top affected SKUs in the chosen scenario."""

    system_prompt = _EMAIL_SYSTEM
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
        _t0 = time.monotonic()
        _stage_started = datetime.now(timezone.utc).isoformat()
        enriched_event = await SignalMonitorAgent().run(raw_event, user_id=user_id)
        try:
            enriched_event = EnrichedEvent(**enriched_event).model_dump()
        except ValidationError as exc:
            store.log_agent_run({
                "rec_id": rec_id, "agent_name": "signal_monitor_validation", "model": MODEL_BUILDER,
                "output_payload": {"validation_error": str(exc)},
                "started_at": _stage_started, "ended_at": datetime.now(timezone.utc).isoformat(),
            })
            raise
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "signal_monitor", "model": MODEL_BUILDER,
            "input_payload": raw_event, "output_payload": enriched_event,
            "started_at": _stage_started,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": int((time.monotonic() - _t0) * 1000),
        })
        _progress(rec_id, "signal_monitor", "done",
                  f"Confidence {enriched_event.get('confidence_score', '?')} · {len(enriched_event.get('hs_codes', []))} HS codes")

        # ── Stage 2: BOM Mapper ─────────────────────────────────────────
        _progress(rec_id, "bom_mapper", "running", "Mapping SKUs to HS codes…")
        _t0 = time.monotonic()
        _stage_started = datetime.now(timezone.utc).isoformat()
        bom_analysis = await BOMMapperAgent().run(enriched_event, bom_rows, user_id=user_id)
        try:
            bom_analysis = BOMAnalysis(**bom_analysis).model_dump()
        except ValidationError as exc:
            store.log_agent_run({
                "rec_id": rec_id, "agent_name": "bom_mapper_validation", "model": MODEL_BUILDER,
                "output_payload": {"validation_error": str(exc)},
                "started_at": _stage_started, "ended_at": datetime.now(timezone.utc).isoformat(),
            })
            raise
        affected = len(bom_analysis.get("affected_skus", []))
        exposure = bom_analysis.get("total_annual_tariff_impact_usd", 0)
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "bom_mapper", "model": MODEL_BUILDER,
            "input_payload": {"event_id": event_id, "bom_id": bom_id},
            "output_payload": {"affected": affected, "exposure_usd": exposure},
            "started_at": _stage_started,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": int((time.monotonic() - _t0) * 1000),
        })
        _progress(rec_id, "bom_mapper", "done",
                  f"{affected} SKUs affected · ${exposure:,.0f}/yr exposure")

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
        _t0 = time.monotonic()
        _stage_started = datetime.now(timezone.utc).isoformat()
        top_scenario = ranked[0]
        emails = await _draft_emails(enriched_event, bom_analysis, top_scenario)
        store.log_agent_run({
            "rec_id": rec_id, "agent_name": "hitl_gate", "model": MODEL_PLANNER,
            "input_payload": {"scenario": top_scenario.get("strategy")},
            "output_payload": {"emails_drafted": len(emails), "status": "awaiting_approval"},
            "started_at": _stage_started,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": int((time.monotonic() - _t0) * 1000),
        })
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
