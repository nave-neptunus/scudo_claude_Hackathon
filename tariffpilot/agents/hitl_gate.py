"""HITL Gate Agent — human authorization + email drafting with double confirmation."""

import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path
import anthropic

MODEL = "claude-sonnet-4-6"

EMAIL_SYSTEM = """<instructions>
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
[
  {
    "to_supplier": "Supplier Name",
    "subject": "Strategic Supply Partnership — Re-routing Request [SKU-XXX]",
    "body": "full email body text",
    "sku_references": ["SKU-001", "SKU-002"],
    "priority": "HIGH"
  }
]
No markdown. Return ONLY the JSON array.
</output_format>"""


class HITLGateAgent:
    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.client = anthropic.AsyncAnthropic()
        self.output_dir = Path("output")
        self.email_dir = self.output_dir / "emails"
        self.output_dir.mkdir(exist_ok=True)
        self.email_dir.mkdir(exist_ok=True)

    async def run(
        self,
        enriched_event: dict,
        bom_analysis: dict,
        scenarios: list[dict],
        ranked_scenarios: list[dict],
    ) -> dict:
        print("\n" + "=" * 70)
        print("  TARIFFPILOT — HUMAN-IN-THE-LOOP AUTHORIZATION GATE")
        print("=" * 70)

        self._display_event_summary(enriched_event, bom_analysis)
        self._display_scenario_table(ranked_scenarios)

        chosen = await self._get_human_choice(ranked_scenarios)

        if chosen is None:
            package = {
                "status": "REJECTED",
                "chosen_scenario": None,
                "emails": [],
                "authorized_at": datetime.utcnow().isoformat(),
            }
            print("\n[HITL] Decision: REJECTED — no action taken.")
            return package

        print(f"\n[HITL] Generating supplier emails for '{chosen['strategy']}' scenario...")
        emails = await self._draft_emails(enriched_event, chosen)

        self._display_email_preview(emails)

        confirmed = await self._get_send_confirmation(emails)

        if confirmed:
            self._write_emails(emails, chosen["strategy"])
            status = "EXECUTED"
            print(f"\n[HITL] {len(emails)} email(s) written to {self.email_dir}/")
        else:
            status = "DRAFTED_NOT_SENT"
            print("\n[HITL] Emails drafted but NOT sent. Saved to output log.")

        package = {
            "status": status,
            "chosen_scenario": chosen,
            "emails": emails,
            "authorized_at": datetime.utcnow().isoformat(),
            "email_dir": str(self.email_dir) if confirmed else None,
        }
        return package

    def _display_event_summary(self, event: dict, bom: dict):
        print(f"\nEvent: {event.get('event_id', 'N/A')} — {event.get('description', 'N/A')}")
        print(f"Rate:  {event.get('old_rate_pct', 0):.0f}% → {event.get('new_rate_pct', 0):.0f}%  |  "
              f"Confidence: {event.get('confidence_score', 0):.0%}  |  "
              f"Effective: {event.get('effective_date', 'TBD')}")
        print(f"BOM:   {bom.get('affected_sku_count', 0)} affected SKUs  |  "
              f"Total exposure: ${bom.get('total_annual_tariff_impact_usd', 0):,.0f}/yr")

    def _display_scenario_table(self, scenarios: list[dict]):
        print("\n" + "-" * 70)
        print(f"  {'SCENARIO':<14} {'COST DELTA/YR':>14} {'LEAD TIME':>10} {'COVERAGE':>10} {'RISK':>6}")
        print("-" * 70)
        for i, s in enumerate(scenarios, 1):
            strategy = s.get("strategy", "unknown").upper().replace("_", "-")
            delta = s.get("annual_cost_delta_usd", 0)
            delta_str = f"+${delta:,.0f}" if delta >= 0 else f"-${abs(delta):,.0f}"
            lead = f"{s.get('lead_time_months', '?')} mo"
            cov = f"{s.get('supplier_coverage_pct', 0):.0f}%"
            risk = f"{s.get('risk_score', 0):.2f}"
            print(f"  [{i}] {strategy:<12} {delta_str:>14} {lead:>10} {cov:>10} {risk:>6}")
        print("-" * 70)
        print("  [4] Request more information")
        print("  [0] Reject — take no action")
        print("-" * 70)

    async def _get_human_choice(self, scenarios: list[dict]) -> dict | None:
        if self.demo_mode:
            print("\n[DEMO MODE] Auto-selecting scenario 1 (reshore)")
            await asyncio.sleep(0.5)
            return scenarios[0] if scenarios else None

        choice = self._get_human_input(
            "\nSelect scenario [1-3], 4 for more info, 0 to reject: ",
            valid=["0", "1", "2", "3", "4"],
        )

        if choice == "0":
            return None
        if choice == "4":
            print("\n[HITL] Status set to NEEDS_MORE_INFO — no action taken.")
            return None

        idx = int(choice) - 1
        if 0 <= idx < len(scenarios):
            return scenarios[idx]
        return None

    def _get_human_input(self, prompt: str, valid: list[str]) -> str:
        while True:
            try:
                response = input(prompt).strip()
                if response in valid:
                    return response
                print(f"  Please enter one of: {', '.join(valid)}")
            except (EOFError, KeyboardInterrupt):
                print("\n[HITL] Input interrupted — defaulting to reject")
                return "0"

    async def _draft_emails(self, event: dict, scenario: dict) -> list[dict]:
        prompt = (
            f"Tariff Event:\n{json.dumps(event, indent=2)}\n\n"
            f"Chosen Strategy:\n{json.dumps(scenario, indent=2)}"
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=EMAIL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            emails = json.loads(text)
            return emails if isinstance(emails, list) else []
        except Exception:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
        return []

    def _display_email_preview(self, emails: list[dict]):
        print(f"\n[HITL] {len(emails)} email(s) drafted:")
        print("-" * 70)
        for i, email in enumerate(emails, 1):
            print(f"\n  Email {i} of {len(emails)}")
            print(f"  TO:      {email.get('to_supplier', 'Unknown')}")
            print(f"  SUBJECT: {email.get('subject', 'No subject')}")
            print(f"  SKUs:    {', '.join(email.get('sku_references', []))}")
            body = email.get("body", "")
            preview = body[:200] + "..." if len(body) > 200 else body
            print(f"\n  {preview}\n")
        print("-" * 70)

    async def _get_send_confirmation(self, emails: list[dict]) -> bool:
        if self.demo_mode:
            print("\n[DEMO MODE] Auto-confirming email send")
            await asyncio.sleep(0.3)
            return True

        confirm = self._get_human_input(
            f"\nSend {len(emails)} email(s) to suppliers? [yes/no]: ",
            valid=["yes", "no", "y", "n"],
        )
        return confirm in ("yes", "y")

    def _write_emails(self, emails: list[dict], strategy: str):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        for i, email in enumerate(emails, 1):
            supplier = email.get("to_supplier", "unknown").replace(" ", "_").replace("/", "_")
            filename = self.email_dir / f"{ts}_{strategy}_{i:02d}_{supplier}.txt"
            with open(filename, "w") as f:
                f.write(f"TO: {email.get('to_supplier', '')}\n")
                f.write(f"SUBJECT: {email.get('subject', '')}\n")
                f.write(f"PRIORITY: {email.get('priority', 'NORMAL')}\n")
                f.write(f"SKU REFS: {', '.join(email.get('sku_references', []))}\n")
                f.write(f"GENERATED: {datetime.utcnow().isoformat()}Z\n")
                f.write("\n" + "-" * 50 + "\n\n")
                f.write(email.get("body", ""))
            print(f"  Wrote: {filename}")
