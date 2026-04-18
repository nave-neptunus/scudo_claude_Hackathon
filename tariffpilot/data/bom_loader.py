"""BOM loader — supports JSON and CSV. Ships with a 10-SKU sample."""

import os
import json
import csv
from pathlib import Path

SAMPLE_BOM = [
    {
        "sku": "IC-8542-001",
        "description": "Application Processor SoC",
        "hs_code": "8542.31.00",
        "supplier": "TSMC Manufacturing",
        "supplier_country": "China",
        "annual_volume_units": 500000,
        "unit_cost_usd": 45.00,
        "annual_spend_usd": 22500000,
        "alt_suppliers": ["Samsung Foundry (Korea)", "GlobalFoundries (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "GlobalFoundries (US)",
        "lead_time_weeks": 16,
        "critical_path": True,
    },
    {
        "sku": "IC-8541-002",
        "description": "Power Management IC",
        "hs_code": "8541.10.00",
        "supplier": "Analog Devices China",
        "supplier_country": "China",
        "annual_volume_units": 2000000,
        "unit_cost_usd": 3.50,
        "annual_spend_usd": 7000000,
        "alt_suppliers": ["Texas Instruments (US)", "Infineon (Germany)"],
        "has_domestic_alt": True,
        "alt_supplier": "Texas Instruments (US)",
        "lead_time_weeks": 8,
        "critical_path": True,
    },
    {
        "sku": "PCB-8534-003",
        "description": "Main Logic Board — 12-layer PCB",
        "hs_code": "8534.00.00",
        "supplier": "Shenzhen PCB Co",
        "supplier_country": "China",
        "annual_volume_units": 300000,
        "unit_cost_usd": 28.00,
        "annual_spend_usd": 8400000,
        "alt_suppliers": ["TTM Technologies (US)", "Jabil Mexico"],
        "has_domestic_alt": True,
        "alt_supplier": "TTM Technologies (US)",
        "lead_time_weeks": 12,
        "critical_path": True,
    },
    {
        "sku": "IC-8542-004",
        "description": "WiFi 6E + Bluetooth 5.3 Combo Chip",
        "hs_code": "8542.39.00",
        "supplier": "MediaTek China",
        "supplier_country": "China",
        "annual_volume_units": 800000,
        "unit_cost_usd": 8.75,
        "annual_spend_usd": 7000000,
        "alt_suppliers": ["Qualcomm (US)", "Broadcom (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "Qualcomm (US)",
        "lead_time_weeks": 14,
        "critical_path": False,
    },
    {
        "sku": "CAP-8532-005",
        "description": "MLCC Capacitors — 100nF 0402",
        "hs_code": "8532.24.00",
        "supplier": "Murata China",
        "supplier_country": "China",
        "annual_volume_units": 50000000,
        "unit_cost_usd": 0.008,
        "annual_spend_usd": 400000,
        "alt_suppliers": ["Murata Japan", "TDK (Japan)", "KEMET (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "KEMET (US)",
        "lead_time_weeks": 6,
        "critical_path": False,
    },
    {
        "sku": "MEM-8542-006",
        "description": "LPDDR5 Memory Die — 16GB",
        "hs_code": "8542.32.00",
        "supplier": "ChangXin Memory (China)",
        "supplier_country": "China",
        "annual_volume_units": 600000,
        "unit_cost_usd": 32.00,
        "annual_spend_usd": 19200000,
        "alt_suppliers": ["SK Hynix (Korea)", "Micron (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "Micron (US)",
        "lead_time_weeks": 20,
        "critical_path": True,
    },
    {
        "sku": "CON-8536-007",
        "description": "USB-C Port Controller",
        "hs_code": "8536.90.00",
        "supplier": "Suzhou Connector Co",
        "supplier_country": "China",
        "annual_volume_units": 1500000,
        "unit_cost_usd": 1.20,
        "annual_spend_usd": 1800000,
        "alt_suppliers": ["Molex (US)", "TE Connectivity (Switzerland)"],
        "has_domestic_alt": True,
        "alt_supplier": "Molex (US)",
        "lead_time_weeks": 4,
        "critical_path": False,
    },
    {
        "sku": "OPT-9001-008",
        "description": "Camera Module — 50MP CMOS",
        "hs_code": "9001.90.00",
        "supplier": "OFilm Technology (China)",
        "supplier_country": "China",
        "annual_volume_units": 400000,
        "unit_cost_usd": 22.00,
        "annual_spend_usd": 8800000,
        "alt_suppliers": ["LG Innotek (Korea)", "Sharp (Japan)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 24,
        "critical_path": True,
    },
    {
        "sku": "BAT-8507-009",
        "description": "Lithium Polymer Battery Pack — 5000mAh",
        "hs_code": "8507.60.00",
        "supplier": "CATL (China)",
        "supplier_country": "China",
        "annual_volume_units": 500000,
        "unit_cost_usd": 18.00,
        "annual_spend_usd": 9000000,
        "alt_suppliers": ["Samsung SDI (Korea)", "LG Energy Solution (Korea)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 18,
        "critical_path": True,
    },
    {
        "sku": "DISP-8524-010",
        "description": "OLED Display Panel — 6.7 inch",
        "hs_code": "8524.11.00",
        "supplier": "BOE Technology (China)",
        "supplier_country": "China",
        "annual_volume_units": 500000,
        "unit_cost_usd": 55.00,
        "annual_spend_usd": 27500000,
        "alt_suppliers": ["Samsung Display (Korea)", "LG Display (Korea)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 22,
        "critical_path": True,
    },
]


def load_bom(path: str | None = None) -> list[dict]:
    env_path = os.getenv("TARIFFPILOT_BOM_PATH")
    target = path or env_path

    if not target:
        return SAMPLE_BOM

    p = Path(target)
    if not p.exists():
        print(f"[BOMLoader] Warning: {target} not found, using sample BOM")
        return SAMPLE_BOM

    if p.suffix.lower() == ".json":
        with open(p) as f:
            return json.load(f)

    if p.suffix.lower() in (".csv", ".tsv"):
        delim = "\t" if p.suffix.lower() == ".tsv" else ","
        rows = []
        with open(p, newline="") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                rows.append({
                    "sku": row.get("sku", ""),
                    "description": row.get("description", ""),
                    "hs_code": row.get("hs_code", ""),
                    "supplier": row.get("supplier", ""),
                    "supplier_country": row.get("supplier_country", ""),
                    "annual_volume_units": int(row.get("annual_volume_units", 0)),
                    "unit_cost_usd": float(row.get("unit_cost_usd", 0)),
                    "annual_spend_usd": float(row.get("annual_spend_usd", 0)),
                    "alt_suppliers": [],
                    "has_domestic_alt": False,
                    "alt_supplier": None,
                    "lead_time_weeks": int(row.get("lead_time_weeks", 12)),
                    "critical_path": row.get("critical_path", "").lower() == "true",
                })
        return rows

    print(f"[BOMLoader] Unsupported format: {p.suffix}, using sample BOM")
    return SAMPLE_BOM
