from __future__ import annotations
"""Supabase-backed store — same interface as store.py.

The 15 DB methods delegate to live Supabase queries via the service-role client.
The 4 progress methods (_init_progress, push_progress, get_progress,
get_progress_since) remain in-memory; SSE pipeline state is ephemeral.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from db.supabase_client import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    def __init__(self):
        self._progress: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # BOMs
    # ------------------------------------------------------------------
    def create_bom(self, name: str, user_id: str = "demo") -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "uploaded_at": _now(),
            "deleted_at": None,
        }
        result = db.table("boms").insert(row).execute()
        return result.data[0] if result.data else row

    def add_bom_rows(self, bom_id: str, rows: list[dict]) -> list[dict]:
        row_objs = []
        for r in rows:
            row_objs.append({
                "id": str(uuid.uuid4()),
                "bom_id": bom_id,
                "sku_code": r.get("sku_code") or r.get("sku", ""),
                "description": r.get("description", ""),
                "supplier_name": r.get("supplier_name") or r.get("supplier", ""),
                "supplier_country": r.get("supplier_country", ""),
                "tier": int(r.get("tier", 1)),
                "annual_quantity": int(r.get("annual_quantity") or r.get("annual_volume_units", 0)),
                "unit_cost_usd": float(r.get("unit_cost_usd", 0)),
                "hs_code": r.get("hs_code"),
                "annual_spend_usd": float(r.get("annual_spend_usd", 0)),
                "has_domestic_alt": bool(r.get("has_domestic_alt", False)),
                "alt_supplier": r.get("alt_supplier"),
                "lead_time_weeks": r.get("lead_time_weeks"),
                "critical_path": bool(r.get("critical_path", False)),
            })
        result = db.table("bom_rows").insert(row_objs).execute()
        return result.data if result.data else row_objs

    def list_boms(self, user_id: str = "demo") -> list[dict]:
        result = (
            db.table("boms")
            .select("*")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .execute()
        )
        return result.data or []

    def get_bom(self, bom_id: str) -> dict | None:
        bom_res = db.table("boms").select("*").eq("id", bom_id).execute()
        if not bom_res.data:
            return None
        bom = bom_res.data[0]
        rows = self.get_bom_rows(bom_id)
        return {**bom, "rows": rows}

    def get_bom_rows(self, bom_id: str) -> list[dict]:
        result = db.table("bom_rows").select("*").eq("bom_id", bom_id).execute()
        return result.data or []

    def soft_delete_bom(self, bom_id: str):
        db.table("boms").update({"deleted_at": _now()}).eq("id", bom_id).execute()

    # ------------------------------------------------------------------
    # Tariff Events
    # ------------------------------------------------------------------
    def upsert_event(self, event: dict) -> dict:
        event_id = event.get("id") or str(uuid.uuid4())
        row = {
            "id": event_id,
            "source": event.get("source", "manual"),
            "published_at": event.get("published_at", _now()),
            "title": event.get("title", ""),
            "url": event.get("url") or f"manual:{event_id}",
            "hs_codes": event.get("hs_codes", []),
            "jurisdictions": event.get("jurisdictions", []),
            "rate_change_bps": event.get("rate_change_bps"),
            "raw_excerpt": event.get("raw_excerpt", event.get("description", "")),
            "content_hash": event.get("content_hash") or str(hash(event.get("title",""))),
            "created_at": event.get("created_at", _now()),
        }
        result = db.table("tariff_events").upsert(row, on_conflict="id").execute()
        stored = result.data[0] if result.data else row
        # Return enriched copy with original event fields
        return {**event, **stored}

    def list_events(self) -> list[dict]:
        result = (
            db.table("tariff_events")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_event(self, event_id: str) -> dict | None:
        result = db.table("tariff_events").select("*").eq("id", event_id).execute()
        return result.data[0] if result.data else None

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    def create_recommendation(self, event_id: str, bom_id: str, user_id: str = "demo") -> dict:
        rec_id = str(uuid.uuid4())
        row = {
            "id": rec_id,
            "user_id": user_id,
            "event_id": event_id,
            "bom_id": bom_id,
            "status": "running",
            "draft_email": None,
            "ranked_scenarios": None,
            "enriched_event": None,
            "bom_analysis": None,
            "approved_at": None,
            "created_at": _now(),
        }
        result = db.table("recommendations").insert(row).execute()
        return result.data[0] if result.data else row

    def update_recommendation(self, rec_id: str, updates: dict):
        db.table("recommendations").update(updates).eq("id", rec_id).execute()

    def get_recommendation(self, rec_id: str) -> dict | None:
        result = db.table("recommendations").select("*").eq("id", rec_id).execute()
        return result.data[0] if result.data else None

    def list_recommendations(self, user_id: str = "demo") -> list[dict]:
        result = (
            db.table("recommendations")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # Agent Runs (audit log)
    # ------------------------------------------------------------------
    def log_agent_run(self, entry: dict):
        row = {
            "id": entry.get("id") or str(uuid.uuid4()),
            "user_id": entry.get("user_id"),
            "agent_name": entry.get("agent_name", ""),
            "model": entry.get("model", ""),
            "input_payload": entry.get("input_payload"),
            "output_payload": entry.get("output_payload"),
            "latency_ms": entry.get("latency_ms"),
            "started_at": entry.get("started_at", _now()),
            "ended_at": entry.get("ended_at"),
        }
        db.table("agent_runs").insert(row).execute()

    def get_agent_runs(self, user_id: str | None = None) -> list[dict]:
        q = db.table("agent_runs").select("*").order("started_at", desc=True).limit(100)
        if user_id:
            q = q.eq("user_id", user_id)
        result = q.execute()
        return result.data or []

    # ------------------------------------------------------------------
    # Pipeline Progress (in-memory, ephemeral)
    # ------------------------------------------------------------------
    def init_progress(self, rec_id: str):
        self._progress[rec_id] = []

    def push_progress(self, rec_id: str, event: dict):
        if rec_id not in self._progress:
            self._progress[rec_id] = []
        self._progress[rec_id].append(event)

    def get_progress(self, rec_id: str) -> list[dict]:
        return self._progress.get(rec_id, [])

    def get_progress_since(self, rec_id: str, offset: int) -> list[dict]:
        return self._progress.get(rec_id, [])[offset:]


store = SupabaseStore()
