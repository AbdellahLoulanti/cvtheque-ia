"""Client Supabase, test de connexion et accès aux candidats / Storage."""

from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.config import (
    STORAGE_BUCKET_CVS,
    SUPABASE_KEY,
    SUPABASE_URL,
    is_supabase_configured,
)

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


# --- Candidats ---

def candidat_exists(chemin_fichier: str) -> bool:
    response = (
        get_supabase()
        .table("candidats")
        .select("id")
        .eq("chemin_fichier", chemin_fichier)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def insert_candidat(row: dict[str, Any]) -> dict[str, Any]:
    response = get_supabase().table("candidats").insert(row).execute()
    return response.data[0]


# --- Storage ---

def upload_cv(path: str, data: bytes, content_type: str) -> None:
    get_supabase().storage.from_(STORAGE_BUCKET_CVS).upload(
        path, data, {"content-type": content_type}
    )


def delete_cv(path: str) -> None:
    get_supabase().storage.from_(STORAGE_BUCKET_CVS).remove([path])
