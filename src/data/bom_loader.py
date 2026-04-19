from __future__ import annotations
"""BOM loader — supports JSON and CSV. Ships with a 10-SKU sample."""

import io
import os
import json
import csv
from pathlib import Path

COFFEE_GRINDER_BOM = [
    {
        "sku": "CG-BURR-01",
        "description": "64mm Flat Steel Burr Set",
        "hs_code": "8208.30.00",
        "supplier": "SSP Grinding",
        "supplier_country": "China",
        "annual_volume_units": 5000,
        "unit_cost_usd": 15.00,
        "annual_spend_usd": 75000,
        "alt_suppliers": ["Mazzer (Italy)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 8,
        "critical_path": True,
    },
    {
        "sku": "CG-MOT-02",
        "description": "250W AC Induction Motor",
        "hs_code": "8501.40.40",
        "supplier": "Nidec Motor",
        "supplier_country": "Vietnam",
        "annual_volume_units": 5000,
        "unit_cost_usd": 25.00,
        "annual_spend_usd": 125000,
        "alt_suppliers": [],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 12,
        "critical_path": True,
    },
    {
        "sku": "CG-HSG-03",
        "description": "Die-Cast Aluminum Housing",
        "hs_code": "7616.99.50",
        "supplier": "Catcher Technology",
        "supplier_country": "Taiwan",
        "annual_volume_units": 5000,
        "unit_cost_usd": 10.00,
        "annual_spend_usd": 50000,
        "alt_suppliers": [],
        "has_domestic_alt": True,
        "alt_supplier": "Protolabs (US)",
        "lead_time_weeks": 6,
        "critical_path": False,
    }
]

COFFEE_SHIRTS_BOM = [
    {
        "sku": "TSH-BLK-01",
        "description": "100% Cotton Blank T-Shirts",
        "hs_code": "6109.10.00",
        "supplier": "Gildan",
        "supplier_country": "Honduras",
        "annual_volume_units": 20000,
        "unit_cost_usd": 3.50,
        "annual_spend_usd": 70000,
        "alt_suppliers": ["Hanes (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "Hanes (US)",
        "lead_time_weeks": 4,
        "critical_path": True,
    },
    {
        "sku": "TSH-INK-02",
        "description": "Plastisol Screen Printing Ink (Black)",
        "hs_code": "3215.19.00",
        "supplier": "Rutland Ink",
        "supplier_country": "China",
        "annual_volume_units": 500,
        "unit_cost_usd": 45.00,
        "annual_spend_usd": 22500,
        "alt_suppliers": [],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 3,
        "critical_path": False,
    }
]

COFFEE_BEANS_BOM = [
    {
        "sku": "BEAN-ARA-01",
        "description": "Green Arabica Coffee Beans (Unroasted)",
        "hs_code": "0901.11.00",
        "supplier": "Sul de Minas Coop",
        "supplier_country": "Brazil",
        "annual_volume_units": 100000,
        "unit_cost_usd": 4.10,
        "annual_spend_usd": 410000,
        "alt_suppliers": ["Antigua Estate (Guatemala)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 6,
        "critical_path": True,
    },
    {
        "sku": "PKG-KFT-02",
        "description": "Kraft Paper Stand-Up Pouches with Valve",
        "hs_code": "4819.40.00",
        "supplier": "PackPlus Packaging",
        "supplier_country": "China",
        "annual_volume_units": 80000,
        "unit_cost_usd": 0.45,
        "annual_spend_usd": 36000,
        "alt_suppliers": [],
        "has_domestic_alt": True,
        "alt_supplier": "US Packaging",
        "lead_time_weeks": 6,
        "critical_path": False,
    }
]


def load_bom(path: str | None = None) -> list[dict]:
    env_path = os.getenv("TARIFFPILOT_BOM_PATH")
    target = path or env_path

    if not target:
        return SAMPLE_BOM

    p = Path(target)
    if not p.exists():
        print(f"[BOMLoader] Warning: {target} not found, using Grinder BOM as default fallback")
        return COFFEE_GRINDER_BOM

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

    print(f"[BOMLoader] Unsupported format: {p.suffix}, using Grinder BOM as default")
    return COFFEE_GRINDER_BOM


def extract_pdf_text(pdf_file: bytes | io.IOBase) -> str:
    """Extract all text from a PDF file using pdfplumber. Returns concatenated page text."""
    import pdfplumber

    if isinstance(pdf_file, (bytes, bytearray)):
        pdf_file = io.BytesIO(pdf_file)

    pages = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n".join(pages)
