"""HITL Gate Agent — human authorization + email drafting (Groq via OpenAI SDK)."""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from openai import AsyncOpenAI

MODEL = "llama-3.3-70b-versatile"

EMAIL_SYSTEM = """<instructions>
You are a professional supply chain communications specialist. Draft supplier notification
emails based on the approved re-routing strategy.
</instructions>
<context>
Formal business language. Reference specific SKUs, volumes, timelines.
Sign as "Supply Chain Team, [Company Name]".
</context>
<task>
One email per unique supplier in top_sku_actions. Each email: explain the re-sourcing
decision, reference SKUs, state qualification timeline, request response within 5 business days.
</task>
<output_format>
Return ONLY valid JSON array:
[{"to_supplier":"string","subject":"string","body":"string","sku_references":["SKU"],"priority":"HIGH"}]
No markdown. Return ONLY the JSON array.
</output_format>"""


class HITLGateAgent:
    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        )
        self.output_dir = Path("output")
        self.email_dir = self.output_dir / "emails"
        self.output_dir.mkdir(exist_ok=True)
        self.email_dir.mkdir(exist_ok=True)

    async def run(self, enriched_event, bom_analysis, scenarios, ranked_scenarios) -> dict:
        print("\n" + "=" * 70)
        print("  TARIFFPILOT — HUMAN-IN-THE-LOOP AUTHORIZATION GATE")
        print("=" * 70)
        self._display_event_summary(enriched_event, bom_analysis)
        self._display_scenario_table(ranked_scenarios)

        chosen = await self._get_human_choice(ranked_scenarios)
        if chosen is None:
            print("\n[HITL] Decision: REJECTED — no action taken.")
            return {"status": "REJECTED", "chosen_scenario": None, "emails": [],
                    "authorized_at": datetime.utcnow().isoformat()}

        print(f"\n[HITL] Generating emails for '{chosen['strategy']}' scenario...")
        emails = await self._draft_emails(enriched_event, chosen)
        self._display_email_preview(emails)
        confirmed = await self._get_send_confirmation(emails)

        if confirmed:
            self._write_emails(emails, chosen["strategy"])
            status = "EXECUTED"
            print(f"\n[HITL] {len(emails)} email(s) written to {self.email_dir}/")
        else:
            status = "DRAFTED_NOT_SENT"
            print("\n[HITL] Emails drafted but NOT sent.")

        return {
            "status": status, "chosen_scenario": chosen, "emails": emails,
            "authorized_at": datetime.utcnow().isoformat(),
            "email_dir": str(self.email_dir) if confirmed else None,
        }

    def _display_event_summary(self, event, bom):
        print(f"\nEvent: {event.get('event_id','N/A')} — {event.get('description','N/A')}")
        print(f"Rate:  {event.get('old_rate_pct',0):.0f}% → {event.get('new_rate_pct',0):.0f}%  |  "
              f"Confidence: {event.get('confidence_score',0):.0%}  |  Effective: {event.get('effective_date','TBD')}")
        print(f"BOM:   {bom.get('affected_sku_count',0)} affected SKUs  |  "
              f"Total exposure: ${bom.get('total_annual_tariff_impact_usd',0):,.0f}/yr")

    def _display_scenario_table(self, scenarios):
        print("\n" + "-" * 70)
        print(f"  {'SCENARIO':<14} {'COST DELTA/YR':>14} {'LEAD TIME':>10} {'COVERAGE':>10} {'RISK':>6}")
        print("-" * 70)
        for i, s in enumerate(scenarios, 1):
            strat = s.get("strategy", "unknown").upper().replace("_", "-")
            delta = s.get("annual_cost_delta_usd", 0)
            ds = f"+${delta:,.0f}" if delta >= 0 else f"-${abs(delta):,.0f}"
            lead = f"{s.get('lead_time_months','?')} mo"
            cov = f"{int(s.get('supplier_coverage_pct', 0))}%"
            risk = f"{s.get('risk_score', 0):.2f}"
            print(f"  [{i}] {strat:<12} {ds:>14} {lead:>10} {cov:>10} {risk:>6}")
        print("-" * 70)
        print("  [4] Request more information   [0] Reject")
        print("-" * 70)

    async def _get_human_choice(self, scenarios):
        if self.demo_mode:
            print("\n[DEMO MODE] Auto-selecting scenario 1")
            await asyncio.sleep(0.3)
            return scenarios[0] if scenarios else None
        choice = self._prompt_user("\nSelect scenario [1-3], 4=more info, 0=reject: ", ["0","1","2","3","4"])
        if choice in ("0", "4"):
            return None
        idx = int(choice) - 1
        return scenarios[idx] if 0 <= idx < len(scenarios) else None

    def _prompt_user(self, prompt, valid):
        while True:
            try:
                r = input(prompt).strip()
                if r in valid:
                    return r
                print(f"  Enter one of: {', '.join(valid)}")
            except (EOFError, KeyboardInterrupt):
                print("\n[HITL] Interrupted — defaulting to reject")
                return "0"

    async def _draft_emails(self, event, scenario) -> list[dict]:
        prompt = (f"Tariff Event:\n{json.dumps(event, indent=2)}\n\n"
                  f"Chosen Strategy:\n{json.dumps(scenario, indent=2)}")
        response = await self.client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": EMAIL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
        )
        text = (response.choices[0].message.content or "").strip()
        emails = self._parse_email_json(text)
        if emails:
            return emails
        # Fallback: generate basic emails from scenario data without another API call
        return self._fallback_emails(event, scenario)

    def _parse_email_json(self, text: str) -> list[dict]:
        # Strip any markdown fences (```json, ```JSON, ```, etc.)
        import re
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text.strip())
        text = text.strip()
        try:
            result = json.loads(text)
            return result if isinstance(result, list) else []
        except Exception:
            start, end = text.find("["), text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
        return []

    def _fallback_emails(self, event: dict, scenario: dict) -> list[dict]:
        """Generate basic emails from scenario data when LLM parse fails."""
        actions = scenario.get("top_sku_actions", [])
        if not actions:
            return []
        # Group by new_supplier
        by_supplier: dict[str, list] = {}
        for a in actions:
            sup = a.get("new_supplier", "Unknown Supplier")
            by_supplier.setdefault(sup, []).append(a)
        emails = []
        effective = event.get("effective_date", "2026-05-01")
        strategy = scenario.get("strategy", "re-routing").replace("_", "-")
        for supplier, acts in by_supplier.items():
            skus = [a["sku"] for a in acts]
            emails.append({
                "to_supplier": supplier,
                "subject": f"Strategic Supply Partnership — {strategy.title()} Request [{', '.join(skus[:2])}]",
                "body": (
                    f"Dear {supplier} Supply Team,\n\n"
                    f"Due to new tariff measures effective {effective}, we are initiating a "
                    f"{strategy} strategy for the following SKUs: {', '.join(skus)}.\n\n"
                    f"We would like to begin supplier qualification discussions immediately. "
                    f"Please respond within 5 business days with your capacity and lead time.\n\n"
                    f"Best regards,\nSupply Chain Team"
                ),
                "sku_references": skus,
                "priority": "HIGH",
            })
        return emails

    def _display_email_preview(self, emails):
        print(f"\n[HITL] {len(emails)} email(s) drafted:")
        print("-" * 70)
        for i, e in enumerate(emails, 1):
            print(f"\n  Email {i}: TO {e.get('to_supplier','?')} | {e.get('subject','')}")
            body = e.get("body", "")
            print(f"  {(body[:200]+'...') if len(body)>200 else body}\n")
        print("-" * 70)

    async def _get_send_confirmation(self, emails) -> bool:
        if self.demo_mode:
            print("\n[DEMO MODE] Auto-confirming send")
            await asyncio.sleep(0.2)
            return True
        confirm = self._prompt_user(f"\nSend {len(emails)} email(s)? [yes/no]: ", ["yes","no","y","n"])
        return confirm in ("yes", "y")

    def _write_emails(self, emails, strategy):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        for i, e in enumerate(emails, 1):
            supplier = e.get("to_supplier", "unknown").replace(" ", "_").replace("/", "_")
            fname = self.email_dir / f"{ts}_{strategy}_{i:02d}_{supplier}.txt"
            with open(fname, "w") as f:
                f.write(f"TO: {e.get('to_supplier','')}\nSUBJECT: {e.get('subject','')}\n"
                        f"PRIORITY: {e.get('priority','NORMAL')}\n"
                        f"SKU REFS: {', '.join(e.get('sku_references',[]))}\n"
                        f"GENERATED: {datetime.utcnow().isoformat()}Z\n\n{'-'*50}\n\n"
                        f"{e.get('body','')}")
            print(f"  Wrote: {fname}")
