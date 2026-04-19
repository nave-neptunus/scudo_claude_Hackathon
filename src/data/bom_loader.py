from __future__ import annotations
"""BOM loader — supports JSON and CSV. Ships with a 10-SKU sample."""

import io
import os
import json
import csv
from pathlib import Path

SAMPLE_BOM = [
    {
        "sku": "EB-MTR-01",
        "description": "BLDC Hub Motor Assembly - 1000W",
        "hs_code": "8501.32.45",
        "supplier": "Bafang Electric",
        "supplier_country": "China",
        "annual_volume_units": 15000,
        "unit_cost_usd": 185.00,
        "annual_spend_usd": 2775000,
        "alt_suppliers": ["Bosch eBike Systems (Germany)", "Yamaha (Japan)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 10,
        "critical_path": True,
    },
    {
        "sku": "EB-BAT-03",
        "description": "18650 Lithium-Ion Battery Array - 48V 15Ah",
        "hs_code": "8507.60.00",
        "supplier": "Sunwoda Electronic",
        "supplier_country": "China",
        "annual_volume_units": 15000,
        "unit_cost_usd": 240.00,
        "annual_spend_usd": 3600000,
        "alt_suppliers": ["Panasonic (Japan)", "LG Energy (Korea)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 14,
        "critical_path": True,
    },
    {
        "sku": "EB-MAG-04",
        "description": "Sintered Neodymium Permanent Magnets (NdFeB)",
        "hs_code": "8505.11.00",
        "supplier": "JL MAG Rare-Earth",
        "supplier_country": "China",
        "annual_volume_units": 300000,
        "unit_cost_usd": 4.50,
        "annual_spend_usd": 1350000,
        "alt_suppliers": ["Shin-Etsu (Japan)", "Hitachi Metals (Japan)"],
        "has_domestic_alt": False,
        "alt_supplier": None,
        "lead_time_weeks": 8,
        "critical_path": True,
    },
    {
        "sku": "EB-CTRL-02",
        "description": "FOC Vector Control PCB with MOSFETs",
        "hs_code": "8537.10.91",
        "supplier": "VinSmart EMS",
        "supplier_country": "Vietnam",
        "annual_volume_units": 15000,
        "unit_cost_usd": 85.00,
        "annual_spend_usd": 1275000,
        "alt_suppliers": ["Foxconn (Taiwan)", "Plexus (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "Plexus (US)",
        "lead_time_weeks": 12,
        "critical_path": True,
    },
    {
        "sku": "EB-ENC-05",
        "description": "Die-Cast Aluminum Enclosure IP67",
        "hs_code": "7616.99.50",
        "supplier": "Catcher Technology",
        "supplier_country": "Taiwan",
        "annual_volume_units": 15000,
        "unit_cost_usd": 18.00,
        "annual_spend_usd": 270000,
        "alt_suppliers": ["Catcher (China)", "Protolabs (US)"],
        "has_domestic_alt": True,
        "alt_supplier": "Protolabs (US)",
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


def extract_pdf_text(pdf_file: bytes | io.IOBase) -> str:
    """Extract all text from a PDF file using pdfplumber. Returns concatenated page text."""
    try:
        import pdfplumber
    except ImportError:
        os.system("pip install pdfplumber -q")
        import pdfplumber

    if isinstance(pdf_file, (bytes, bytearray)):
        pdf_file = io.BytesIO(pdf_file)

    pages = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n".join(pages)
