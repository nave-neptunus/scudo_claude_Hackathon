from __future__ import annotations
"""Compile a plain-text business context block from a user's business_profiles row."""

from db.supabase_store import store


def compile_business_context(user_id: str) -> str:
    """Query business_profiles for user_id and return a formatted context block.

    Returns an empty string if no profile exists, so agents remain functional
    without a profile (e.g. during system-wide Signal Monitor polls).
    """
    result = (
        store._supabase_profile(user_id)
        if hasattr(store, "_supabase_profile")
        else _fetch_profile(user_id)
    )
    if not result:
        return ""

    parts = ["<business_context>"]
    if result.get("company_name"):
        parts.append(f"Company: {result['company_name']}")
    if result.get("industry"):
        parts.append(f"Industry: {result['industry']}")
    if result.get("products"):
        parts.append(f"Products: {result['products']}")
    if result.get("supplier_countries"):
        countries = ", ".join(result["supplier_countries"])
        parts.append(f"Supplier countries: {countries}")
    if result.get("monthly_import_usd"):
        parts.append(f"Monthly import volume: ${result['monthly_import_usd']:,.2f}")
    if result.get("supplier_relationships"):
        parts.append(f"Supplier relationships: {result['supplier_relationships']}")
    if result.get("tariff_concern"):
        parts.append(f"Primary tariff concern: {result['tariff_concern']}")
    if result.get("tone_preference"):
        parts.append(f"Preferred tone: {result['tone_preference']}")
    if result.get("pdf_text"):
        parts.append(f"Uploaded document excerpts:\n{result['pdf_text'][:2000]}")
    parts.append("</business_context>")
    return "\n".join(parts)


def _fetch_profile(user_id: str) -> dict | None:
    from db.supabase_client import db
    result = db.table("business_profiles").select("*").eq("id", user_id).execute()
    return result.data[0] if result.data else None
