from __future__ import annotations
"""Tavily web search client — replaces BraveMCPClient."""

import os
from datetime import datetime


class TavilyClient:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")

    async def search(self, query: str, count: int = 5) -> list[dict]:
        if self.api_key:
            return await self._real_search(query, count)
        return await self._mock_search(query, count)

    async def _real_search(self, query: str, count: int) -> list[dict]:
        try:
            from tavily import TavilyClient as _Tavily
            client = _Tavily(api_key=self.api_key)
            response = client.search(query=query, max_results=count)
            results = response.get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("content", r.get("description", "")),
                    "published": r.get("published_date", datetime.now().strftime("%Y-%m-%d")),
                }
                for r in results
            ]
        except Exception as e:
            print(f"[TavilyClient] Real search failed ({e}), falling back to mock")
            return await self._mock_search(query, count)

    async def _mock_search(self, query: str, count: int) -> list[dict]:
        import asyncio
        import random
        await asyncio.sleep(0.3)
        q = query.lower()

        semiconductor_results = [
            {
                "title": "USTR Announces 84% Tariff on Chinese Semiconductor Imports — Effective May 1 2026",
                "url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2026/april/semiconductor-tariffs",
                "description": "The Office of the United States Trade Representative announced sweeping tariffs on integrated circuits and advanced packaging from China under Section 301. HTS codes 8541, 8542 face an 84% ad valorem rate effective May 1, 2026. Korea and Taiwan exempted.",
                "published": "2026-04-15",
            },
            {
                "title": "Supply Chain Impact: Chip Tariffs Hit PCB and Assembly Sector",
                "url": "https://electronicdesign.com/supply-chain/chip-tariff-impact-2026",
                "description": "Industry analysts warn that the new semiconductor tariffs will ripple into printed circuit board assemblies (HTS 8534, 8537) and electromechanical components. Companies with >30% China-sourced silicon face immediate BOM cost increases of 18-40%.",
                "published": "2026-04-16",
            },
            {
                "title": "CHIPS Act Domestic Exemptions Apply to HTS 8542.31 and 8542.39",
                "url": "https://commerce.gov/chips-act/exemptions-2026",
                "description": "US Department of Commerce confirms that chips manufactured in CHIPS Act-funded fabs are exempt from the new tariffs. Qualifying products must have >50% US value content.",
                "published": "2026-04-15",
            },
            {
                "title": "Goldman Sachs: Semiconductor Tariffs Could Add $4.2B to US Electronics Costs",
                "url": "https://goldmansachs.com/research/semiconductor-tariff-impact",
                "description": "Goldman Sachs research estimates the new China semiconductor tariffs will add $4.2 billion annually to US electronics manufacturing costs.",
                "published": "2026-04-16",
            },
            {
                "title": "USMCA Partners Exempt: Mexico and Canada Semiconductor Trade Unaffected",
                "url": "https://cbp.gov/trade/tariffs/usmca-semiconductor-exemption-2026",
                "description": "US Customs confirms that semiconductor imports from Mexico and Canada under USMCA are not subject to the new Section 301 tariffs.",
                "published": "2026-04-16",
            },
        ]

        generic_results = [
            {
                "title": f"Trade Policy Update: {query[:50]}",
                "url": "https://ustr.gov/trade-policy/2026",
                "description": "USTR confirms new tariff measures affecting goods matching query context. Affected HS codes include ranges in Chapters 84, 85, and 90. Effective date: May 1, 2026.",
                "published": datetime.now().strftime("%Y-%m-%d"),
            },
            {
                "title": "Supply Chain Advisory: Multi-Country Sourcing Recommended",
                "url": "https://supplychainbrain.com/advisory/2026-tariff-response",
                "description": "Supply chain advisors recommend dual-sourcing strategies for components affected by 2026 tariff wave.",
                "published": datetime.now().strftime("%Y-%m-%d"),
            },
        ]

        if any(k in q for k in ["semiconductor", "chip", "integrated circuit", "8541", "8542"]):
            pool = semiconductor_results
        else:
            pool = generic_results + random.sample(semiconductor_results, min(2, len(semiconductor_results)))

        return pool[:count]
