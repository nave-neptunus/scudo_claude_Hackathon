# TariffShield — Project Specification

> Source of truth for the TariffShield multi-agent tariff detection and supply chain re-routing system.

---

## 1. Overview

TariffShield is a web application that protects small business importers from sudden tariff shocks. Owners upload a Bill of Materials (BOM) describing their product SKUs and supplier countries. The system continuously monitors government tariff feeds, detects events that affect the user's supply chain, scores SKU-level exposure, models alternative sourcing scenarios in parallel, and drafts supplier outreach emails. A human-in-the-loop (HITL) approval gate is required before any external action (email send) is executed.

**Primary user:** Owner-operators of small importing businesses who need automated early warning and concrete re-sourcing options without giving up control of supplier communications.

**Core value loop:**
1. Upload BOM CSV.
2. System watches for tariff events 24/7.
3. On a relevant event: agents score impact, propose three sourcing scenarios, and draft an outreach email.
4. User reviews the ranked scenarios and approves (or edits) the email with one click.

---

## 2. Tech Stack

| Layer | Technology | Deployment |
|------|------------|------------|
| Frontend | React + Vite + Tailwind CSS | Vercel |
| Backend API | FastAPI (Python 3.11+) | Fly.io |
| Database & Auth | Supabase (PostgreSQL + Supabase Auth) | Supabase Cloud |
| LLM — All agents | `llama-3.3-70b-versatile` (Llama 3.3 70B) | Groq API |
| Agent orchestration | Python `asyncio.gather()` for parallel sub-agents | Backend process |
| External signal sources | Federal Register REST API (no key), Tavily API | Backend pollers |
| Tariff rate source | Census Bureau Schedule B API, USITC HTS API (no key) | BOM Mapper |
| Email generation | CLI-first (Groq API — Llama 3.3 70B, not MCP) | Backend |

**Model assignment rules:**
- All agents use `llama-3.3-70b-versatile` (Llama 3.3 70B via Groq API).
- Groq provides free, low-latency inference — no cost per token.
- Every agent system prompt receives a `business_context` block compiled by `utils/context_builder.py::compile_business_context()` from the user's `business_profiles` row. This personalizes tariff alerts, scenario suggestions, and email drafts to the specific business.

**Data sources by agent:**
- Signal Monitor: Federal Register REST API (no key) + Tavily API (`TAVILY_API_KEY`)
- BOM Mapper: Census Bureau Schedule B API (`CENSUS_API_KEY`) → USITC HTS API (no key)
- All external data lookups are live and real-time — no local dataset caching.

---

## 3. Agent Architecture

TariffShield is composed of four top-level agents. Agents communicate exclusively via structured JSON messages with validated schemas. No agent may invoke an external side-effect (email send, API write) without passing through the HITL Gate.

### 3.1 Agent 1 — Signal Monitor
**Role:** Detect new tariff events in real time.

**Inputs:**
- **Federal Register REST API** — `GET https://www.federalregister.gov/api/v1/documents?conditions[term]=tariff` (polled; no API key required). Supersedes the RSS feed; provides structured `document_number`, `abstract`, `effective_on`, and `agencies` fields.
- **Tavily API** — web search queries scoped to tariff-related terms and jurisdictions (supplemental signal source; requires `TAVILY_API_KEY`).

**Outputs (JSON):**
```json
{
  "event_id": "uuid",
  "source": "federal_register | brave_search",
  "published_at": "ISO-8601",
  "title": "string",
  "url": "string",
  "hs_codes": ["string"],
  "jurisdictions": ["ISO-3166 country codes"],
  "rate_change_bps": "int | null",
  "raw_excerpt": "string"
}
```

**Responsibilities:**
- Deduplicate by `document_number` (Federal Register canonical ID) + `content_hash`.
- Extract HS codes, jurisdictions, effective date, and rate delta from each document abstract using Llama 3.3 70B via Groq.
- Persist enriched event to `tariff_events` table.
- Trigger downstream `bom_mapper` runs for any user whose BOM intersects the event.

### 3.2 Agent 2 — BOM Mapper
**Role:** Map a user's BOM SKUs to affected HS codes and quantify supplier exposure across tiers.

**Inputs:**
- User BOM rows from Supabase.
- One `tariff_event` JSON.

**Outputs (JSON):**
```json
{
  "user_id": "uuid",
  "event_id": "uuid",
  "exposed_skus": [
    {
      "sku_id": "uuid",
      "sku_code": "string",
      "tier": 1,
      "supplier_country": "ISO-3166",
      "exposure_score": 0.0,
      "annual_spend_usd": 0.0,
      "matched_hs_code": "string"
    }
  ]
}
```

**Responsibilities:**
- Normalize and validate BOM rows on upload.
- Score Tier 1–4 supplier exposure (Tier 1 = direct supplier; Tier 4 = upstream raw materials).
- Use Llama 3.3 70B to clean and standardize each BOM product description into trade-standard terminology before any HS code lookup.
- **Census Bureau Schedule B API** (`CENSUS_API_KEY`) — submit cleaned description to resolve HTS code candidates; select the top-confidence match.
- **USITC HTS API** (no key) — given the resolved HTS code, query `https://hts.usitc.gov/api/search?query=[HTS_CODE]` to retrieve the live general rate, special rates, and Column 2 rate.
- Both steps are encapsulated in a single `lookup_tariff_rate(product_description)` function. No local caching — all lookups are live.

### 3.3 Agent 3 — Scenario Modeler
**Role:** For each exposed SKU group, generate three alternative sourcing scenarios in parallel.

**Sub-agents (run via `asyncio.gather()`):**
1. **Reshore** — domestic supplier alternatives.
2. **Nearshore** — suppliers in nearby low-tariff jurisdictions.
3. **Dual-source** — split the SKU across the existing supplier and a new region to hedge.

**Each sub-agent output (JSON):**
```json
{
  "scenario_type": "reshore | nearshore | dual_source",
  "candidate_suppliers": [
    {
      "name": "string",
      "country": "ISO-3166",
      "estimated_unit_cost_usd": 0.0,
      "moq": 0,
      "lead_time_days": 0,
      "source_confidence": 0.0
    }
  ],
  "landed_cost_delta_pct": 0.0,
  "lead_time_change_days": 0,
  "qualitative_notes": "string"
}
```

**Responsibilities:**
- All three sub-agents MUST be dispatched concurrently with `asyncio.gather()`. Sequential calls are a spec violation.
- Sub-agent generation uses Llama 3.3 70B via Groq.
- The Orchestrator ranks the three scenarios afterward by composite score (cost delta, lead time delta, confidence).

### 3.4 Agent 4 — Execution + HITL Gate
**Role:** Rank scenarios, draft a supplier outreach email, and require explicit human approval before sending.

**Inputs:**
- Ranked scenarios from Agent 3.
- User profile (company name, signature, tone preferences).

**Outputs (JSON):**
```json
{
  "recommendation_id": "uuid",
  "ranked_scenarios": [ "..." ],
  "draft_email": {
    "to": "string | null",
    "subject": "string",
    "body": "string",
    "scenario_ref": "scenario_id"
  },
  "status": "awaiting_approval"
}
```

**Responsibilities:**
- Email drafting is performed via the **Groq API** using Llama 3.3 70B, NOT via MCP.
- The HITL Gate agent critiques the draft for tone, factual grounding, and missing fields before it is presented to the user.
- Status transitions: `awaiting_approval → approved | edited | rejected`. Only `approved` (with or without user edits) may trigger an outbound send.

---

## 4. Data Flow

```
[Federal Register API]   [Tavily API]
            \             /
             v           v
        [Signal Monitor] -----> tariff_events (Supabase)
                                       |
                                       v
                              [BOM Mapper] ---> exposure_scores (Supabase)
                                       |
                                       v
              ┌─────────[Scenario Modeler — asyncio.gather()]─────────┐
              v                        v                              v
         [Reshore]               [Nearshore]                    [Dual-source]
              \________________________|______________________________/
                                       v
                              [Orchestrator ranking — llama-3.3-70b]
                                       |
                                       v
                            [Execution + HITL Gate]
                                       |
                                       v
                            [HITL critique — llama-3.3-70b]
                                       |
                                       v
                          [User approval UI — React]
                                       |
                                       v
                  (only if approved) → outbound supplier email
```

**Storage rules:**
- BOM data: Supabase (`boms`, `bom_rows`).
- Tariff events: cached locally in Supabase (`tariff_events`); raw payloads kept for 90 days.
- Scenarios and draft emails: Supabase (`scenarios`, `recommendations`).
- Inter-agent messages: validated JSON in-memory; persisted to `agent_runs` for audit.

---

## 5. API Endpoints

All endpoints are FastAPI routes hosted on Fly.io. Authentication uses Supabase JWTs forwarded in the `Authorization: Bearer <token>` header.

### Onboarding
| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/v1/onboarding` | Submit onboarding survey + upload BOM CSV and optional PDFs (multipart). Creates `business_profile` and initial BOM rows. Returns `{ business_profile_id, bom_id }`. |

### Auth & Profile
| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/v1/me` | Current user profile. |
| PATCH  | `/api/v1/me` | Update company name, signature, tone preferences. |

### BOM Management
| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/v1/boms` | Upload a BOM CSV (multipart). Returns parsed rows + validation report. |
| GET    | `/api/v1/boms` | List user's BOMs. |
| GET    | `/api/v1/boms/{bom_id}` | Get a single BOM with rows. |
| DELETE | `/api/v1/boms/{bom_id}` | Soft-delete a BOM. |

### Tariff Events
| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/v1/events` | List recent tariff events affecting the user (paginated). |
| GET    | `/api/v1/events/{event_id}` | Get a single event with exposure breakdown. |

### Scenarios & Recommendations
| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/v1/events/{event_id}/analyze` | Trigger BOM Mapper + Scenario Modeler for the event. Returns recommendation id. |
| GET    | `/api/v1/recommendations/{rec_id}` | Get ranked scenarios + draft email. |
| PATCH  | `/api/v1/recommendations/{rec_id}/email` | User edits to the draft email body. |
| POST   | `/api/v1/recommendations/{rec_id}/approve` | HITL approval — triggers outbound send. |
| POST   | `/api/v1/recommendations/{rec_id}/reject` | HITL rejection — closes the recommendation. |

### Internal / Admin
| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/v1/internal/poll-signals` | Cron-triggered Signal Monitor run (token-gated). |
| GET    | `/api/v1/health` | Liveness probe for Fly.io. |

---

## 6. Database Schema

PostgreSQL via Supabase. Row-Level Security (RLS) is enabled on every user-scoped table; users may only access rows where `user_id = auth.uid()`.

### `users` (managed by Supabase Auth, extended)
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | from `auth.users` |
| company_name | text | |
| signature | text | email signature block |
| tone_preference | text | e.g. `formal`, `casual` |
| created_at | timestamptz | default `now()` |

### `business_profiles`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| user_id | uuid FK → users.id | unique — one profile per user |
| industry | text | |
| products_description | text | free-text from survey |
| supplier_countries | text[] | ISO-3166 |
| import_volume_usd | numeric(14,2) | monthly estimate |
| existing_relationships | text nullable | |
| tariff_concerns | text nullable | |
| extracted_pdf_text | text nullable | pdfplumber output from uploaded docs |
| created_at | timestamptz | default `now()` |

RLS: `user_id = auth.uid()`. One row per user; upsert on re-submit.

### `boms`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| user_id | uuid FK → users.id | |
| name | text | |
| uploaded_at | timestamptz | |
| deleted_at | timestamptz nullable | soft delete |

### `bom_rows`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| bom_id | uuid FK → boms.id | |
| sku_code | text | |
| description | text | |
| supplier_name | text | |
| supplier_country | text | ISO-3166 |
| tier | int | 1–4 |
| annual_quantity | int | |
| unit_cost_usd | numeric(12,2) | |
| hs_code | text nullable | filled by BOM Mapper if missing |
| annual_spend_usd | numeric(14,2) nullable | computed: `annual_quantity × unit_cost_usd` |
| has_domestic_alt | boolean nullable | |
| alt_supplier | text nullable | |
| lead_time_weeks | int nullable | |
| critical_path | boolean nullable | |

### `tariff_events`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| source | text | `federal_register` \| `tavily` |
| published_at | timestamptz | |
| title | text | |
| url | text unique | |
| hs_codes | text[] | |
| jurisdictions | text[] | |
| rate_change_bps | int nullable | |
| raw_excerpt | text | |
| content_hash | text unique | dedup key |
| created_at | timestamptz | |

### `exposure_scores`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| user_id | uuid FK | |
| event_id | uuid FK → tariff_events.id | |
| bom_row_id | uuid FK → bom_rows.id | |
| matched_hs_code | text | |
| exposure_score | numeric(5,4) | 0.0–1.0 |
| computed_at | timestamptz | |

### `scenarios`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| recommendation_id | uuid FK → recommendations.id | |
| scenario_type | text | `reshore` \| `nearshore` \| `dual_source` |
| payload | jsonb | full sub-agent output |
| landed_cost_delta_pct | numeric(6,3) | |
| lead_time_change_days | int | |
| rank | int | set by Planner |

### `recommendations`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| user_id | uuid FK | |
| event_id | uuid FK | |
| bom_id | uuid FK → boms.id | |
| draft_email | jsonb | `{to, subject, body, scenario_ref}` |
| ranked_scenarios | jsonb nullable | ordered scenario list after Orchestrator ranking |
| enriched_event | jsonb nullable | full tariff event payload used during analysis |
| bom_analysis | jsonb nullable | BOM Mapper exposure output used during analysis |
| status | text | `awaiting_approval` \| `approved` \| `edited` \| `rejected` |
| approved_at | timestamptz nullable | |
| created_at | timestamptz | |

### `agent_runs` (audit log)
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| user_id | uuid FK nullable | null for system-wide Signal Monitor runs |
| agent_name | text | `signal_monitor` \| `bom_mapper` \| `scenario_modeler` \| `execution_hitl` |
| model | text | `llama-3.3-70b-versatile` |
| input_payload | jsonb | |
| output_payload | jsonb | |
| latency_ms | int | |
| started_at | timestamptz | |
| ended_at | timestamptz | |

---

## 7. Environment Variables

| Variable | Required by | Notes |
|----------|-------------|-------|
| `GROQ_API_KEY` | Backend — all agents | Groq API access (free tier available) |
| `SUPABASE_URL` | Backend + Frontend | Project URL |
| `SUPABASE_ANON_KEY` | Frontend | Public client key |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | Bypasses RLS for Signal Monitor poller only |
| `TAVILY_API_KEY` | Backend — Signal Monitor | Tavily web search |
| `CENSUS_API_KEY` | Backend — BOM Mapper | Census Bureau Schedule B API |

No other external API keys are required. Federal Register API and USITC HTS API are unauthenticated.

---

## 8. Constraints

These are non-negotiable invariants. Any code change that violates them is a spec regression.

1. **HITL gate is mandatory.** No outbound email may be sent without an explicit `POST /api/v1/recommendations/{rec_id}/approve` call originating from the authenticated user. Auto-send is forbidden under any condition, including retries.
2. **Validate every inter-agent message.** Each agent's output JSON MUST conform to its declared schema (Pydantic models in the backend) before being passed to the next agent. Invalid payloads halt the pipeline and are logged to `agent_runs`.
3. **Parallel sub-agents must use `asyncio.gather()`.** The three Scenario Modeler sub-agents (Reshore, Nearshore, Dual-source) MUST be dispatched concurrently. Sequential `await` calls or thread pools are not acceptable substitutes.
4. **CLI-first email generation.** The supplier outreach email is drafted via the Groq API (Llama 3.3 70B). MCP is explicitly out of scope for this flow.
5. **Model discipline.** All agents use `llama-3.3-70b-versatile` via the Groq API. Do not swap the model without updating this spec.
6. **No silent external actions.** Any agent capable of side effects (email, supplier API write, webhook) MUST route through the HITL Gate. Read-only external calls (Federal Register API, Tavily API, Census Schedule B API, USITC HTS API) are exempt but must be logged.
7. **Auditability.** Every agent invocation is recorded in `agent_runs` with input, output, model, and latency. Recommendations preserve their full scenario lineage so users can re-inspect any past decision.
8. **Tenant isolation.** Supabase RLS policies are required on every user-scoped table. No backend endpoint may bypass RLS using the service-role key except for the internal Signal Monitor poller.
