# TariffShield — TODO

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
