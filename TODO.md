# TariffShield — TODO

## PHASE: Tavily Migration (replace Brave Search)

### Signal Monitor → src/tools/ + src/agents/

- [x] Add `tavily-python` to `requirements.txt`; create `src/tools/tavily_client.py` with a `TavilyClient` class that calls `tavily.search(query, max_results=count)` and normalizes each result to `{title, url, description, published}` (Tavily returns `content`, not `description` — map it); mirror the same async `search(query, count) -> list[dict]` signature as the old `BraveMCPClient` — Owner: Builder — Priority: high
- [x] In `src/agents/signal_monitor.py`: replace `from tools.mcp_client import BraveMCPClient` with `from tools.tavily_client import TavilyClient`; rename `self.brave = BraveMCPClient()` → `self.tavily = TavilyClient()`; rename Groq tool definition from `"brave_search"` → `"tavily_search"`; rename `_execute_brave_search` → `_execute_tavily_search`; update `tc.function.name == "brave_search"` check to `"tavily_search"` — Owner: Builder — Priority: high
- [x] In `.env`: rename `BRAVE_API_KEY` → `TAVILY_API_KEY` and rename `TAVILY_KEY` → `TAVILY_API_KEY` (consolidate to one correct key name); delete `src/tools/mcp_client.py` — Owner: Builder — Priority: high

---

## PHASE: Supabase Migration

### Client setup + schema

- [x] Add `supabase` to `requirements.txt`; create `src/db/supabase_client.py` that instantiates `create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)` and exports a singleton `db` — Owner: Builder — Priority: high
- [x] Write `db/migrations/001_initial_schema.sql` with all 8 tables from SPEC.md §6 (`business_profiles`, `boms`, `bom_rows`, `tariff_events`, `exposure_scores`, `scenarios`, `recommendations`, `agent_runs`) including the 5 extra `bom_rows` columns and 4 extra `recommendations` columns added to SPEC.md; add `CREATE POLICY` RLS statements for every user-scoped table — Owner: Builder — Priority: high
- [x] Run migration against the Supabase project; verify all tables created and RLS active — Owner: Builder — Priority: high

### Store replacement

- [x] Write `src/db/supabase_store.py` implementing the same 17-method interface as `store.py` (`create_bom`, `add_bom_rows`, `list_boms`, `get_bom`, `get_bom_rows`, `soft_delete_bom`, `upsert_event`, `list_events`, `get_event`, `create_recommendation`, `update_recommendation`, `get_recommendation`, `list_recommendations`, `log_agent_run`, `get_agent_runs`) backed by live Supabase queries — Owner: Builder — Priority: high
- [x] Keep `_progress` dict and its 4 methods (`init_progress`, `push_progress`, `get_progress`, `get_progress_since`) in-memory inside `supabase_store.py` — SSE pipeline state is ephemeral and does not need DB persistence — Owner: Builder — Priority: high

### Wire up + cleanup

- [x] Replace `from store import store` with `from db.supabase_store import store` in `src/api.py` and `src/pipeline.py`; delete `src/store.py` and `src/data/store.json` — Owner: Builder — Priority: high
- [x] Fix `.env` typos: rename `GROQ_API` → `GROQ_API_KEY` and `TAVILY_KEY` → `TAVILY_API_KEY`; confirm `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` are read via `os.getenv` in `supabase_client.py` — Owner: Builder — Priority: high

---

## PHASE: Onboarding

### Survey UI + file uploads → React frontend

- [x] Build multi-step onboarding survey in React — fields: business name, industry, products (free text), supplier countries (multiselect ISO-3166), monthly import volume USD, existing supplier relationships, biggest tariff concern — Owner: Builder — Priority: high
- [x] Build BOM CSV upload component in React with client-side row validation (required columns: `sku_code`, `description`, `supplier_country`, `unit_cost_usd`) — Owner: Builder — Priority: high
- [x] Build optional PDF upload component in React (accepts multiple files; supplier contracts, tariff rulings, freight invoices) — Owner: Builder — Priority: medium

### Ingestion backend → FastAPI + Supabase

- [x] Add `pdfplumber` to `requirements.txt` and write `extract_pdf_text(pdf_file) -> str` in `data/bom_loader.py`; concatenate all uploaded PDF pages into a single string — Owner: Builder — Priority: medium
- [x] Create `business_profiles` table in Supabase per SPEC.md §6 schema; enable RLS policy `user_id = auth.uid()`; upsert on re-submit — Owner: Builder — Priority: high
- [x] Implement `POST /api/v1/onboarding` FastAPI endpoint — accepts multipart form with survey fields + BOM CSV + optional PDFs; calls `extract_pdf_text()` for each PDF; writes `business_profiles` row and delegates BOM CSV parsing to `data/bom_loader.py`; returns `{ business_profile_id, bom_id }` — Owner: Builder — Priority: high

### Business context injection → all agents

- [x] Write `compile_business_context(user_id) -> str` in `utils/context_builder.py` — queries `business_profiles` row and assembles a plain-text context block (business name, industry, products, supplier countries, import volume, extracted PDF text) for injection into agent system prompts — Owner: Builder — Priority: high
- [x] Thread `business_context` into the system prompt of all four agents (Signal Monitor, BOM Mapper, Scenario Modeler, Execution+HITL) by calling `compile_business_context(user_id)` at the start of each agent run — Owner: Builder — Priority: high

---

## PHASE: Data Integration

### Federal Register REST API → signal_monitor.py

- [x] Add Federal Register REST API client to `signal_monitor.py` — built `tools/federal_register.py` with `FederalRegisterClient`; paginates until no new `document_number`s seen, attaches `content_hash` to each doc — Owner: Builder — Priority: high
- [x] Update dedup logic in `signal_monitor.py` to key on `document_number` as the canonical Federal Register ID in addition to `content_hash`; retire URL-only dedup which breaks on redirects — keyed on `document_number`, persisted in `data/seen_document_numbers.json` — Owner: Builder — Priority: high
- [x] Write `claude-sonnet-4-6` extraction prompt that receives a document `title` + `abstract` and returns a validated JSON object with `hs_codes: list[str]`, `jurisdictions: list[str]` (ISO-3166), `effective_date: str | null`, and `rate_change_bps: int | null`; wrap response in Pydantic before use (Constraint 2) — `EXTRACTION_SYSTEM_PROMPT` + `FedRegDocExtraction` Pydantic model in `signal_monitor.py` — Owner: Builder — Priority: high
- [x] Log every Federal Register API call to `agent_runs` with agent_name `signal_monitor`, input = query params, output = document count returned (Constraint 7 — read-only calls must still be logged) — `_log_agent_run()` appends to `output/agent_runs.jsonl`; called for every HTTP page + every Claude extraction call — Owner: Builder — Priority: high

### Census Bureau Schedule B API + USITC HTS API → bom_mapper.py

- [x] Write `claude-sonnet-4-6` prompt in `bom_mapper.py` that receives a raw BOM `description` and returns a concise, trade-standard product description suitable for Schedule B lookup; apply this cleaning step to every row before any HS code API call — `DESCRIPTION_CLEANER_SYSTEM` prompt + `_clean_description()` method; called as first step in `lookup_tariff_rate()` — Owner: Builder — Priority: high
- [x] Implement Census Schedule B API client in `bom_mapper.py` — submit cleaned description, parse top HTS code candidates and confidence scores, return `{"hs_code": str, "confidence": float}` in a Pydantic model — `_census_schedule_b_lookup()` + `ScheduleBMatch` Pydantic model; `_normalize_hts_code()` converts 10-digit codes to dotted notation — Owner: Builder — Priority: high
- [x] Implement USITC HTS API client in `bom_mapper.py` — `GET https://hts.usitc.gov/api/search?query=[HTS_CODE]`, parse general rate, special rates, and Column 2 rate from the live JSON response, return in a Pydantic model — `_usitc_hts_lookup()` + `HTSRates` model; handles `{"content":[...]}` and bare list responses — Owner: Builder — Priority: high
- [x] Chain Census Schedule B → USITC HTS API into a single `lookup_tariff_rate(product_description)` function in `bom_mapper.py` — no local caching, all lookups are live — `lookup_tariff_rate()` method chains `_clean_description()` → `_census_schedule_b_lookup()` → `_usitc_hts_lookup()`; integrated into `run()` via `_enrich_missing_hs_codes()` — Owner: Builder — Priority: high
