"""Client Supabase et test de connexion."""

from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.config import SUPABASE_KEY, SUPABASE_URL, is_supabase_configured

_client: Client | None = None


def get_supabase() -> Client:
    """Retourne le client Supabase (singleton)."""
    global _client
    if not is_supabase_configured():
        raise RuntimeError(
            "Supabase non configuré : renseigner SUPABASE_URL et SUPABASE_KEY dans .env"
        )
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def test_connection() -> dict[str, Any]:
    """
    Vérifie la connexion Supabase en interrogeant la table candidats.
    Retourne {"ok": bool, "message": str}.
    """
    if not is_supabase_configured():
        return {"ok": False, "message": "Variables SUPABASE_URL / SUPABASE_KEY manquantes"}

    try:
        client = get_supabase()
        # Requête légère : confirme auth + existence de la table
        client.table("candidats").select("id").limit(1).execute()
        return {"ok": True, "message": "Connexion OK"}
    except Exception as exc:  # noqa: BLE001 — message utilisateur
        return {"ok": False, "message": str(exc)}
