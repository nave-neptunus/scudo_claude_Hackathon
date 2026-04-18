from __future__ import annotations
"""TariffShield — FastAPI backend. All endpoints per SPEC.md §5."""

import asyncio
import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from store import store
from pipeline import run_pipeline

app = FastAPI(title="TariffShield API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ────────────────────────────────────────────────────────────────────────────
# Request / response models
# ────────────────────────────────────────────────────────────────────────────

class UserPatch(BaseModel):
    company_name: str | None = None
    signature: str | None = None
    tone_preference: str | None = None


class EmailPatch(BaseModel):
    body: str


class RawEventIn(BaseModel):
    """Manual tariff event submission for triggering pipeline."""
    event_id: str | None = None
    title: str
    description: str
    hs_codes_hint: list[str] = []
    affected_countries_hint: list[str] = []
    rate_change_hint: str = ""
    effective_date_hint: str = ""
    source: str = "manual"
    url: str = ""


class AnalyzeRequest(BaseModel):
    bom_id: str


# ────────────────────────────────────────────────────────────────────────────
# Health
# ────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ────────────────────────────────────────────────────────────────────────────
# Auth & Profile (simplified — single demo user)
# ────────────────────────────────────────────────────────────────────────────

_profile = {
    "id": "demo",
    "company_name": "Acme Imports LLC",
    "signature": "Supply Chain Team\nAcme Imports LLC",
    "tone_preference": "formal",
}


@app.get("/api/v1/me")
def get_me():
    return _profile


@app.patch("/api/v1/me")
def patch_me(body: UserPatch):
    if body.company_name is not None:
        _profile["company_name"] = body.company_name
    if body.signature is not None:
        _profile["signature"] = body.signature
    if body.tone_preference is not None:
        _profile["tone_preference"] = body.tone_preference
    return _profile


# ────────────────────────────────────────────────────────────────────────────
# BOM Management
# ────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/boms")
async def upload_bom(file: UploadFile = File(...)):
    """Accept a CSV or JSON BOM upload. Returns parsed rows + validation report."""
    content = await file.read()
    filename = file.filename or "bom"
    name = filename.rsplit(".", 1)[0]

    rows, errors = [], []

    if filename.endswith(".json"):
        try:
            data = json.loads(content)
            if isinstance(data, list):
                raw_rows = data
            else:
                raw_rows = data.get("rows", data.get("bom", []))
        except Exception as e:
            raise HTTPException(400, f"Invalid JSON: {e}")
        for i, r in enumerate(raw_rows):
            rows.append(_normalize_row(r, i, errors))
    else:
        # CSV
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        for i, r in enumerate(reader):
            rows.append(_normalize_row(dict(r), i, errors))

    if not rows:
        raise HTTPException(400, "No rows found in upload")

    bom = store.create_bom(name)
    stored_rows = store.add_bom_rows(bom["id"], rows)

    return {
        "bom": {**bom, "rows": stored_rows},
        "row_count": len(stored_rows),
        "validation_errors": errors,
    }


def _normalize_row(r: dict, i: int, errors: list) -> dict:
    # flexible field name mapping
    out = {}
    out["sku_code"] = (r.get("sku_code") or r.get("sku") or r.get("SKU", f"SKU-{i:04d}")).strip()
    out["description"] = (r.get("description") or r.get("Description", "")).strip()
    out["supplier_name"] = (r.get("supplier_name") or r.get("supplier") or r.get("Supplier", "")).strip()
    out["supplier_country"] = (r.get("supplier_country") or r.get("country") or r.get("Country", "")).strip()
    out["tier"] = int(r.get("tier") or r.get("Tier") or 1)
    try:
        out["annual_quantity"] = int(float(r.get("annual_quantity") or r.get("annual_volume_units") or r.get("qty") or 0))
    except Exception:
        out["annual_quantity"] = 0
        errors.append(f"Row {i}: invalid annual_quantity")
    try:
        out["unit_cost_usd"] = float(r.get("unit_cost_usd") or r.get("unit_cost") or 0)
    except Exception:
        out["unit_cost_usd"] = 0.0
    out["hs_code"] = (r.get("hs_code") or r.get("HS") or r.get("hts_code") or "").strip() or None
    out["annual_spend_usd"] = float(r.get("annual_spend_usd") or r.get("annual_spend") or
                                     out["annual_quantity"] * out["unit_cost_usd"])
    out["has_domestic_alt"] = str(r.get("has_domestic_alt", "false")).lower() in ("true", "1", "yes")
    out["alt_supplier"] = r.get("alt_supplier") or r.get("alternative_supplier") or None
    out["lead_time_weeks"] = r.get("lead_time_weeks") or r.get("lead_time") or None
    out["critical_path"] = str(r.get("critical_path", "false")).lower() in ("true", "1", "yes")
    return out


@app.get("/api/v1/boms")
def list_boms():
    return store.list_boms()


@app.get("/api/v1/boms/{bom_id}")
def get_bom(bom_id: str):
    bom = store.get_bom(bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    return bom


@app.delete("/api/v1/boms/{bom_id}")
def delete_bom(bom_id: str):
    store.soft_delete_bom(bom_id)
    return {"status": "deleted"}


# ────────────────────────────────────────────────────────────────────────────
# Tariff Events
# ────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/events")
def create_event(body: RawEventIn):
    """Manually submit a tariff event (for demo / testing)."""
    event = {
        "id": body.event_id or str(uuid.uuid4()),
        "source": body.source,
        "title": body.title,
        "description": body.description,
        "url": body.url,
        "hs_codes": body.hs_codes_hint,
        "jurisdictions": body.affected_countries_hint,
        "rate_change_hint": body.rate_change_hint,
        "effective_date_hint": body.effective_date_hint,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "raw_excerpt": body.description,
        "content_hash": str(hash(body.title + body.description)),
        # keep raw fields for orchestrator
        "event_id": body.event_id or str(uuid.uuid4()),
        "hs_codes_hint": body.hs_codes_hint,
        "affected_countries_hint": body.affected_countries_hint,
        "rate_change_hint": body.rate_change_hint,
        "effective_date_hint": body.effective_date_hint,
    }
    stored = store.upsert_event(event)
    return stored


@app.get("/api/v1/events")
def list_events(page: int = 1, per_page: int = 20):
    all_events = store.list_events()
    start = (page - 1) * per_page
    return {
        "events": all_events[start: start + per_page],
        "total": len(all_events),
        "page": page,
        "per_page": per_page,
    }


@app.get("/api/v1/events/{event_id}")
def get_event(event_id: str):
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    # attach recommendations for this event
    recs = [r for r in store.list_recommendations()
            if r["event_id"] == event_id]
    return {**ev, "recommendations": recs}


# ────────────────────────────────────────────────────────────────────────────
# Scenarios & Recommendations
# ────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/events/{event_id}/analyze")
def analyze_event(event_id: str, body: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Trigger BOM Mapper + Scenario Modeler. Returns recommendation_id immediately."""
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    bom = store.get_bom(body.bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")

    rec = store.create_recommendation(event_id, body.bom_id)
    background_tasks.add_task(_run_bg, rec["id"], event_id, body.bom_id)
    return {"recommendation_id": rec["id"], "status": "running"}


def _run_bg(rec_id: str, event_id: str, bom_id: str):
    asyncio.run(run_pipeline(rec_id, event_id, bom_id))


@app.get("/api/v1/recommendations/{rec_id}")
def get_recommendation(rec_id: str):
    rec = store.get_recommendation(rec_id)
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    return rec


@app.get("/api/v1/recommendations")
def list_recommendations():
    return store.list_recommendations()


@app.patch("/api/v1/recommendations/{rec_id}/email")
def patch_email(rec_id: str, body: EmailPatch):
    rec = store.get_recommendation(rec_id)
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    draft = rec.get("draft_email") or {}
    draft["body"] = body.body
    store.update_recommendation(rec_id, {"draft_email": draft, "status": "edited"})
    return store.get_recommendation(rec_id)


@app.post("/api/v1/recommendations/{rec_id}/approve")
def approve_recommendation(rec_id: str):
    """HITL approval — per SPEC constraint 1, this is the only path to send."""
    rec = store.get_recommendation(rec_id)
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    if rec["status"] not in ("awaiting_approval", "edited"):
        raise HTTPException(400, f"Cannot approve from status '{rec['status']}'")
    store.update_recommendation(rec_id, {
        "status": "approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    })
    store.log_agent_run({
        "agent_name": "hitl_gate",
        "action": "approved",
        "rec_id": rec_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    return store.get_recommendation(rec_id)


@app.post("/api/v1/recommendations/{rec_id}/reject")
def reject_recommendation(rec_id: str):
    rec = store.get_recommendation(rec_id)
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    store.update_recommendation(rec_id, {"status": "rejected"})
    store.log_agent_run({
        "agent_name": "hitl_gate",
        "action": "rejected",
        "rec_id": rec_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    return store.get_recommendation(rec_id)


# ────────────────────────────────────────────────────────────────────────────
# SSE — pipeline progress streaming
# ────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/recommendations/{rec_id}/stream")
async def stream_progress(rec_id: str):
    """Server-Sent Events stream of pipeline stage updates."""

    async def event_generator() -> AsyncGenerator[str, None]:
        offset = 0
        while True:
            rec = store.get_recommendation(rec_id)
            events = store.get_progress_since(rec_id, offset)
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"
                offset += 1

            if rec and rec.get("status") in ("awaiting_approval", "approved", "rejected", "error"):
                # pipeline finished — send final state and close
                yield f"data: {json.dumps({'stage': 'done', 'status': rec['status'], 'rec': rec})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ────────────────────────────────────────────────────────────────────────────
# Internal / Admin
# ────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/internal/poll-signals")
async def poll_signals():
    """Trigger Signal Monitor Federal Register poll. Cron-gated in prod."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scudo_claude_Hackathon" / "tariffpilot"))
    from agents.signal_monitor import SignalMonitorAgent

    agent = SignalMonitorAgent()
    try:
        events = await agent.poll_federal_register()
    except AttributeError:
        # Fallback if method not available
        return {"status": "ok", "events_found": 0, "message": "poll_federal_register not available"}

    stored = []
    for ev in events:
        normalized = {
            "id": str(uuid.uuid4()),
            "source": "federal_register",
            "title": ev.get("title", ""),
            "description": ev.get("abstract", ev.get("raw_excerpt", "")),
            "url": ev.get("url", ""),
            "hs_codes": ev.get("hs_codes", []),
            "jurisdictions": ev.get("jurisdictions", []),
            "rate_change_bps": ev.get("rate_change_bps"),
            "published_at": ev.get("published_at", datetime.now(timezone.utc).isoformat()),
            "raw_excerpt": ev.get("raw_excerpt", ""),
            "content_hash": ev.get("content_hash", str(hash(ev.get("title", "")))),
            "event_id": ev.get("document_number", str(uuid.uuid4())),
            "hs_codes_hint": ev.get("hs_codes", []),
            "affected_countries_hint": ev.get("jurisdictions", []),
        }
        stored.append(store.upsert_event(normalized))

    return {"status": "ok", "events_found": len(stored), "events": stored}


@app.get("/api/v1/audit")
def get_audit():
    return store.get_agent_runs()


# ────────────────────────────────────────────────────────────────────────────
# Demo seed — load sample data so the UI has something to show immediately
# ────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/demo/seed")
def seed_demo():
    """Seed the demo event + BOM from the existing sample data."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scudo_claude_Hackathon" / "tariffpilot"))
    from data.bom_loader import SAMPLE_BOM

    # Seed demo event
    demo_event = {
        "id": "USTR-2026-04-SEMI-001",
        "event_id": "USTR-2026-04-SEMI-001",
        "source": "manual",
        "title": "Section 301 — Chinese Semiconductors 0% → 84%",
        "description": "84% tariff on Chinese integrated circuits and advanced semiconductors under Section 301",
        "url": "https://ustr.gov/tariff-actions/2026/section-301-semiconductors",
        "hs_codes": ["8541", "8542", "8534"],
        "jurisdictions": ["CN"],
        "rate_change_hint": "0% → 84%",
        "effective_date_hint": "2026-05-01",
        "hs_codes_hint": ["8541", "8542", "8534"],
        "affected_countries_hint": ["CN"],
        "published_at": "2026-04-01T00:00:00Z",
        "raw_excerpt": "USTR announces 84% Section 301 tariff on Chinese semiconductors effective May 1 2026",
        "content_hash": "demo-seed-001",
    }
    store.upsert_event(demo_event)

    # Seed demo BOM
    if not store.list_boms():
        bom = store.create_bom("Titan-X E-Bike Motor Controller")
        store.add_bom_rows(bom["id"], SAMPLE_BOM)
        return {"seeded": True, "event_id": demo_event["id"], "bom_id": bom["id"]}

    boms = store.list_boms()
    return {"seeded": True, "event_id": demo_event["id"], "bom_id": boms[0]["id"]}
