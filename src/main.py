#!/usr/bin/env python3
from __future__ import annotations
"""TariffPilot entry point."""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    print("ERROR: GROQ_API_KEY environment variable is not set.")
    print("       export GROQ_API_KEY=gsk_...")
    sys.exit(1)

# Default demo tariff event — semiconductor tariffs April 2026
DEMO_EVENT = {
    "event_id": "USTR-2026-04-SEMI-001",
    "description": "84% tariff on Chinese integrated circuits and advanced semiconductors under Section 301",
    "hs_codes_hint": ["8541", "8542", "8534"],
    "affected_countries_hint": ["China"],
    "rate_change_hint": "0% → 84%",
    "effective_date_hint": "2026-05-01",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="TariffPilot — 4-agent tariff response system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --demo                  # Non-interactive demo mode
  python main.py                         # Interactive HITL mode
  python main.py --event my_event.json   # Custom tariff event
  python main.py --bom data/my_bom.json  # Custom BOM file
        """,
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode: non-interactive, auto-approves scenario 1",
    )
    parser.add_argument(
        "--event",
        metavar="FILE",
        help="Path to custom tariff event JSON file",
    )
    parser.add_argument(
        "--bom",
        metavar="FILE",
        help="Path to custom BOM file (JSON or CSV)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # Load event
    raw_event = DEMO_EVENT
    if args.event:
        event_path = Path(args.event)
        if not event_path.exists():
            print(f"ERROR: Event file not found: {args.event}")
            sys.exit(1)
        with open(event_path) as f:
            raw_event = json.load(f)
        print(f"[main] Loaded custom event from {args.event}")
    else:
        print("[main] Using built-in demo tariff event (USTR-2026-04-SEMI-001)")

    # Run pipeline
    from agents.orchestrator import OrchestratorAgent
    orchestrator = OrchestratorAgent(demo_mode=args.demo)

    result = await orchestrator.run(raw_event, bom_path=args.bom)

    status = result.get("package", {}).get("status", "UNKNOWN")
    run_id = result.get("run_id", "unknown")

    print(f"\nDone. Status: {status}")
    print(f"Full audit: output/tariffpilot_result_{run_id}.json")

    if status == "EXECUTED":
        email_dir = result.get("package", {}).get("email_dir")
        if email_dir:
            print(f"Emails:     {email_dir}/")


if __name__ == "__main__":
    asyncio.run(main())
