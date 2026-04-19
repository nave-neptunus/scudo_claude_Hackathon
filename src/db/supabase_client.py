from __future__ import annotations
"""Supabase client singleton — uses service-role key for backend ops.

Falls back gracefully when credentials are not set (local dev mode).
"""

import os
from typing import Any

_url = os.getenv("SUPABASE_URL", "")
_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

db: Any = None

if _url and _key:
    from supabase import create_client, Client
    db = create_client(_url, _key)
