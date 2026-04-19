-- TariffShield initial schema
-- Run once against the Supabase project (service-role key required).
-- All user-scoped tables have RLS enabled; system tables (tariff_events, agent_runs) are open to service role.

-- ─────────────────────────────────────────────────────────────────
-- 1. business_profiles  (extends auth.users; one row per user)
-- ─────────────────────────────────────────────────────────────────
create table if not exists business_profiles (
  id                     uuid primary key references auth.users(id) on delete cascade,
  company_name           text,
  industry               text,
  products               text,
  supplier_countries     text[],
  monthly_import_usd     numeric(14,2),
  supplier_relationships text,
  tariff_concern         text,
  pdf_text               text,
  signature              text,
  tone_preference        text default 'formal',
  created_at             timestamptz default now(),
  updated_at             timestamptz default now()
);

alter table business_profiles enable row level security;

create policy "user_sees_own_profile" on business_profiles
  for all using (id = auth.uid());

-- ─────────────────────────────────────────────────────────────────
-- 2. boms
-- ─────────────────────────────────────────────────────────────────
create table if not exists boms (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users(id) on delete cascade,
  name        text not null,
  uploaded_at timestamptz default now(),
  deleted_at  timestamptz
);

alter table boms enable row level security;

create policy "user_sees_own_boms" on boms
  for all using (user_id = auth.uid());

-- ─────────────────────────────────────────────────────────────────
-- 3. bom_rows  (SPEC §6 cols + 5 extra cols from store.py)
-- ─────────────────────────────────────────────────────────────────
create table if not exists bom_rows (
  id                 uuid primary key default gen_random_uuid(),
  bom_id             uuid references boms(id) on delete cascade,
  sku_code           text not null,
  description        text,
  supplier_name      text,
  supplier_country   text,
  tier               int default 1,
  annual_quantity    int default 0,
  unit_cost_usd      numeric(12,2) default 0,
  hs_code            text,
  -- extra cols
  annual_spend_usd   numeric(14,2) default 0,
  has_domestic_alt   boolean default false,
  alt_supplier       text,
  lead_time_weeks    int,
  critical_path      boolean default false
);

alter table bom_rows enable row level security;

create policy "user_sees_own_bom_rows" on bom_rows
  for all using (
    exists (select 1 from boms b where b.id = bom_rows.bom_id and b.user_id = auth.uid())
  );

-- ─────────────────────────────────────────────────────────────────
-- 4. tariff_events  (system-wide; no per-user RLS needed)
-- ─────────────────────────────────────────────────────────────────
create table if not exists tariff_events (
  id               uuid primary key default gen_random_uuid(),
  source           text,
  published_at     timestamptz,
  title            text,
  url              text unique,
  hs_codes         text[],
  jurisdictions    text[],
  rate_change_bps  int,
  raw_excerpt      text,
  content_hash     text unique,
  created_at       timestamptz default now()
);

-- service role can write; authenticated users can read
alter table tariff_events enable row level security;

create policy "anyone_reads_events" on tariff_events
  for select using (true);

create policy "service_writes_events" on tariff_events
  for insert with check (true);

create policy "service_updates_events" on tariff_events
  for update using (true);

-- ─────────────────────────────────────────────────────────────────
-- 5. exposure_scores
-- ─────────────────────────────────────────────────────────────────
create table if not exists exposure_scores (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid references auth.users(id) on delete cascade,
  event_id         uuid references tariff_events(id) on delete cascade,
  bom_row_id       uuid references bom_rows(id) on delete cascade,
  matched_hs_code  text,
  exposure_score   numeric(5,4),
  computed_at      timestamptz default now()
);

alter table exposure_scores enable row level security;

create policy "user_sees_own_exposure" on exposure_scores
  for all using (user_id = auth.uid());

-- ─────────────────────────────────────────────────────────────────
-- 6. recommendations  (SPEC §6 cols + 4 extra cols from store.py)
-- ─────────────────────────────────────────────────────────────────
create table if not exists recommendations (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid references auth.users(id) on delete cascade,
  event_id         uuid references tariff_events(id) on delete cascade,
  draft_email      jsonb,
  status           text default 'running',
  approved_at      timestamptz,
  created_at       timestamptz default now(),
  -- extra cols
  bom_id           text,
  ranked_scenarios jsonb,
  enriched_event   jsonb,
  bom_analysis     jsonb
);

alter table recommendations enable row level security;

create policy "user_sees_own_recs" on recommendations
  for all using (user_id = auth.uid());

-- ─────────────────────────────────────────────────────────────────
-- 7. scenarios
-- ─────────────────────────────────────────────────────────────────
create table if not exists scenarios (
  id                      uuid primary key default gen_random_uuid(),
  recommendation_id       uuid references recommendations(id) on delete cascade,
  scenario_type           text,
  payload                 jsonb,
  landed_cost_delta_pct   numeric(6,3),
  lead_time_change_days   int,
  rank                    int
);

alter table scenarios enable row level security;

create policy "user_sees_own_scenarios" on scenarios
  for all using (
    exists (select 1 from recommendations r where r.id = scenarios.recommendation_id and r.user_id = auth.uid())
  );

-- ─────────────────────────────────────────────────────────────────
-- 8. agent_runs  (audit log; service role writes, users read own)
-- ─────────────────────────────────────────────────────────────────
create table if not exists agent_runs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid,
  agent_name      text,
  model           text,
  input_payload   jsonb,
  output_payload  jsonb,
  latency_ms      int,
  started_at      timestamptz default now(),
  ended_at        timestamptz
);

alter table agent_runs enable row level security;

create policy "user_reads_own_runs" on agent_runs
  for select using (user_id = auth.uid() or user_id is null);

create policy "service_writes_runs" on agent_runs
  for insert with check (true);
