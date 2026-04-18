"""In-memory store with JSON file persistence. Replaces Supabase for local dev."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

_STORE_FILE = _DATA_DIR / "store.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if _STORE_FILE.exists():
        try:
            return json.loads(_STORE_FILE.read_text())
        except Exception:
            pass
    return {"boms": {}, "bom_rows": {}, "events": {}, "recommendations": {}, "scenarios": {}, "agent_runs": []}


def _save(state: dict):
    _STORE_FILE.write_text(json.dumps(state, indent=2, default=str))


class Store:
    def __init__(self):
        self._state = _load()
        # pipeline progress is ephemeral (not persisted)
        self._progress: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # BOMs
    # ------------------------------------------------------------------
    def create_bom(self, name: str, user_id: str = "demo") -> dict:
        bom_id = str(uuid.uuid4())
        bom = {
            "id": bom_id,
            "user_id": user_id,
            "name": name,
            "uploaded_at": _now(),
            "deleted_at": None,
        }
        self._state["boms"][bom_id] = bom
        self._state["bom_rows"][bom_id] = []
        _save(self._state)
        return bom

    def add_bom_rows(self, bom_id: str, rows: list[dict]):
        existing = self._state["bom_rows"].get(bom_id, [])
        row_objs = []
        for r in rows:
            row_id = str(uuid.uuid4())
            row = {
                "id": row_id,
                "bom_id": bom_id,
                "sku_code": r.get("sku_code") or r.get("sku", ""),
                "description": r.get("description", ""),
                "supplier_name": r.get("supplier_name") or r.get("supplier", ""),
                "supplier_country": r.get("supplier_country", ""),
                "tier": int(r.get("tier", 1)),
                "annual_quantity": int(r.get("annual_quantity") or r.get("annual_volume_units", 0)),
                "unit_cost_usd": float(r.get("unit_cost_usd", 0)),
                "hs_code": r.get("hs_code"),
                # extra fields from sample BOM
                "annual_spend_usd": float(r.get("annual_spend_usd", 0)),
                "has_domestic_alt": r.get("has_domestic_alt", False),
                "alt_supplier": r.get("alt_supplier"),
                "lead_time_weeks": r.get("lead_time_weeks"),
                "critical_path": r.get("critical_path", False),
            }
            row_objs.append(row)
        self._state["bom_rows"][bom_id] = existing + row_objs
        _save(self._state)
        return row_objs

    def list_boms(self, user_id: str = "demo") -> list[dict]:
        return [b for b in self._state["boms"].values()
                if b["user_id"] == user_id and not b.get("deleted_at")]

    def get_bom(self, bom_id: str) -> dict | None:
        bom = self._state["boms"].get(bom_id)
        if not bom:
            return None
        return {**bom, "rows": self._state["bom_rows"].get(bom_id, [])}

    def get_bom_rows(self, bom_id: str) -> list[dict]:
        return self._state["bom_rows"].get(bom_id, [])

    def soft_delete_bom(self, bom_id: str):
        if bom_id in self._state["boms"]:
            self._state["boms"][bom_id]["deleted_at"] = _now()
            _save(self._state)

    # ------------------------------------------------------------------
    # Tariff Events
    # ------------------------------------------------------------------
    def upsert_event(self, event: dict) -> dict:
        event_id = event.get("id") or str(uuid.uuid4())
        event["id"] = event_id
        event.setdefault("created_at", _now())
        self._state["events"][event_id] = event
        _save(self._state)
        return event

    def list_events(self) -> list[dict]:
        return sorted(
            self._state["events"].values(),
            key=lambda e: e.get("created_at", ""),
            reverse=True,
        )

    def get_event(self, event_id: str) -> dict | None:
        return self._state["events"].get(event_id)

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    def create_recommendation(self, event_id: str, bom_id: str, user_id: str = "demo") -> dict:
        rec_id = str(uuid.uuid4())
        rec = {
            "id": rec_id,
            "user_id": user_id,
            "event_id": event_id,
            "bom_id": bom_id,
            "status": "running",
            "draft_email": None,
            "ranked_scenarios": [],
            "enriched_event": None,
            "bom_analysis": None,
            "approved_at": None,
            "created_at": _now(),
        }
        self._state["recommendations"][rec_id] = rec
        _save(self._state)
        return rec

    def update_recommendation(self, rec_id: str, updates: dict):
        if rec_id in self._state["recommendations"]:
            self._state["recommendations"][rec_id].update(updates)
            _save(self._state)

    def get_recommendation(self, rec_id: str) -> dict | None:
        return self._state["recommendations"].get(rec_id)

    def list_recommendations(self, user_id: str = "demo") -> list[dict]:
        return [r for r in self._state["recommendations"].values()
                if r.get("user_id") == user_id]

    # ------------------------------------------------------------------
    # Agent Runs (audit log)
    # ------------------------------------------------------------------
    def log_agent_run(self, entry: dict):
        entry.setdefault("id", str(uuid.uuid4()))
        entry.setdefault("started_at", _now())
        self._state["agent_runs"].append(entry)
        # keep last 1000
        self._state["agent_runs"] = self._state["agent_runs"][-1000:]
        _save(self._state)

    def get_agent_runs(self, user_id: str | None = None) -> list[dict]:
        runs = self._state["agent_runs"]
        if user_id:
            runs = [r for r in runs if r.get("user_id") == user_id]
        return list(reversed(runs))[-100:]

    # ------------------------------------------------------------------
    # Pipeline Progress (SSE)
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


store = Store()
