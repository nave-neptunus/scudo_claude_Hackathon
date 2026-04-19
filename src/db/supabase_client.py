from __future__ import annotations
"""Supabase client singleton — uses service-role key for backend ops."""

import os
from supabase import create_client, Client

_url = os.getenv("SUPABASE_URL", "")
_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not _url or not _key:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

db: Client = create_client(_url, _key)
