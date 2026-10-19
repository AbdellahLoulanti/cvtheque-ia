"""Client Supabase, test de connexion et accès aux candidats, appels d'offres et Storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client, create_client

from app.config import (
    SIGNED_URL_EXPIRES_SECONDS,
    STATUT_ANALYSE,
    STATUT_ERREUR,
    STATUT_IMPORTE,
    STORAGE_BUCKET_AO,
    STORAGE_BUCKET_CVS,
    SUPABASE_KEY,
    SUPABASE_URL,
    is_supabase_configured,
)

_client: Client | None = None

# Colonnes des listes et de la recherche (sans le texte brut ni l'embedding, volumineux)
_SUMMARY_COLUMNS = (
    "id, nom, prenom, poste, experience_annees, competences, technologies, langues, "
    "incertitudes, chemin_fichier, statut, created_at"
)
_DETAIL_COLUMNS = (
    "id, nom, prenom, email, telephone, poste, experience_annees, competences, technologies, "
    "formations, certifications, langues, incertitudes, texte_brut, chemin_fichier, statut, "
    "created_at, updated_at"
)
_MATCHING_COLUMNS = (
    "id, nom, prenom, poste, experience_annees, competences, technologies, certifications, langues, "
    "texte_brut, chemin_fichier, embedding"
)
_AO_SUMMARY_COLUMNS = "id, titre, poste, experience_min_annees, competences_obligatoires, created_at"
_AO_DETAIL_COLUMNS = (
    "id, titre, poste, contexte, responsabilites, competences_obligatoires, competences_souhaitees, "
    "experience_requise, experience_min_annees, technologies, contraintes, profil_ideal, incertitudes, "
    "texte_brut, chemin_fichier, created_at, updated_at"
)
# Colonne absente (lecture) ou inconnue du cache PostgREST (écriture)
_MISSING_COLUMN_CODES = {"42703", "PGRST204"}
_AO_MIGRATION_MESSAGE = (
    "La table appels_offres n'est pas à jour : exécutez "
    "supabase/migrations/004_appels_offres.sql dans Supabase (SQL Editor)."
)


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


def list_candidats() -> list[dict[str, Any]]:
    """Tous les candidats, les plus récents d'abord."""
    response = (
        get_supabase()
        .table("candidats")
        .select(_SUMMARY_COLUMNS)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def get_candidat(candidat_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase()
        .table("candidats")
        .select(_DETAIL_COLUMNS)
        .eq("id", candidat_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def list_candidats_a_analyser(include_analysed: bool = False) -> list[dict[str, Any]]:
    """CV importés pas encore analysés ou en erreur ; tous les CV si include_analysed."""
    statuts = [STATUT_IMPORTE, STATUT_ERREUR]
    if include_analysed:
        statuts.append(STATUT_ANALYSE)
    response = (
        get_supabase()
        .table("candidats")
        .select("id, chemin_fichier, texte_brut")
        .in_("statut", statuts)
        .order("created_at")
        .execute()
    )
    return response.data


def list_candidats_sans_embedding() -> list[dict[str, Any]]:
    """CV analysés dont l'embedding n'a pas encore été calculé."""
    response = (
        get_supabase()
        .table("candidats")
        .select("id, chemin_fichier, poste, experience_annees, technologies, competences")
        .eq("statut", STATUT_ANALYSE)
        .is_("embedding", "null")
        .order("created_at")
        .execute()
    )
    return response.data


def list_candidats_pour_matching() -> list[dict[str, Any]]:
    """CV analysés avec ce qu'il faut pour les comparer à un AO (fiche, texte brut, embedding)."""
    response = (
        get_supabase()
        .table("candidats")
        .select(_MATCHING_COLUMNS)
        .eq("statut", STATUT_ANALYSE)
        .execute()
    )
    return [{**row, "embedding": parse_vector(row.get("embedding"))} for row in response.data]


def match_candidats(
    query_embedding: list[float],
    *,
    limit: int,
    experience_min: float | None,
    experience_max: float | None,
    include_unknown_experience: bool,
) -> list[dict[str, Any]]:
    """Appelle la fonction SQL match_candidats (similarité cosinus pgvector)."""
    try:
        response = (
            get_supabase()
            .rpc(
                "match_candidats",
                {
                    "query_embedding": query_embedding,
                    "match_count": limit,
                    "experience_min": experience_min,
                    "experience_max": experience_max,
                    "include_unknown_experience": include_unknown_experience,
                },
            )
            .execute()
        )
    except APIError as exc:
        if exc.code == "PGRST202":
            raise RuntimeError(
                "La fonction SQL match_candidats est absente : exécutez "
                "supabase/migrations/003_recherche_semantique.sql dans Supabase (SQL Editor)."
            ) from exc
        raise
    return response.data


def update_candidat(candidat_id: str, fields: dict[str, Any]) -> None:
    payload = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
    get_supabase().table("candidats").update(payload).eq("id", candidat_id).execute()


# --- Appels d'offres ---

def insert_appel_offre(row: dict[str, Any]) -> dict[str, Any]:
    try:
        response = get_supabase().table("appels_offres").insert(row).execute()
    except APIError as exc:
        _raise_if_ao_migration_missing(exc)
        raise
    return response.data[0]


def list_appels_offres() -> list[dict[str, Any]]:
    """Tous les appels d'offres, les plus récents d'abord."""
    try:
        response = (
            get_supabase()
            .table("appels_offres")
            .select(_AO_SUMMARY_COLUMNS)
            .order("created_at", desc=True)
            .execute()
        )
    except APIError as exc:
        _raise_if_ao_migration_missing(exc)
        raise
    return response.data


def get_appel_offre(ao_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase()
        .table("appels_offres")
        .select(_AO_DETAIL_COLUMNS)
        .eq("id", ao_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_appel_offre_embedding(ao_id: str) -> list[float] | None:
    response = (
        get_supabase()
        .table("appels_offres")
        .select("embedding")
        .eq("id", ao_id)
        .limit(1)
        .execute()
    )
    return parse_vector(response.data[0].get("embedding")) if response.data else None


def parse_vector(value: Any) -> list[float] | None:
    """PostgREST renvoie les colonnes vector sous forme de texte « [0.1,0.2,…] »."""
    if value is None:
        return None
    return json.loads(value) if isinstance(value, str) else list(value)


def _raise_if_ao_migration_missing(exc: APIError) -> None:
    if exc.code in _MISSING_COLUMN_CODES:
        raise RuntimeError(_AO_MIGRATION_MESSAGE) from exc


# --- Storage ---

def upload_cv(path: str, data: bytes, content_type: str, overwrite: bool = False) -> None:
    _upload(STORAGE_BUCKET_CVS, path, data, content_type, overwrite)


def delete_cv(path: str) -> None:
    get_supabase().storage.from_(STORAGE_BUCKET_CVS).remove([path])


def create_cv_signed_url(path: str, expires_in: int = SIGNED_URL_EXPIRES_SECONDS) -> str:
    """Lien temporaire vers un CV du bucket privé."""
    return _signed_url(STORAGE_BUCKET_CVS, path, expires_in)


def upload_ao(path: str, data: bytes, content_type: str) -> None:
    try:
        _upload(STORAGE_BUCKET_AO, path, data, content_type, overwrite=False)
    except Exception as exc:
        if "bucket not found" in str(exc).casefold():
            raise RuntimeError(_AO_MIGRATION_MESSAGE) from exc
        raise


def delete_ao(path: str) -> None:
    get_supabase().storage.from_(STORAGE_BUCKET_AO).remove([path])


def create_ao_signed_url(path: str, expires_in: int = SIGNED_URL_EXPIRES_SECONDS) -> str:
    """Lien temporaire vers un fichier d'appel d'offres du bucket privé."""
    return _signed_url(STORAGE_BUCKET_AO, path, expires_in)


def _upload(bucket: str, path: str, data: bytes, content_type: str, overwrite: bool) -> None:
    options = {"content-type": content_type}
    if overwrite:
        options["upsert"] = "true"
    get_supabase().storage.from_(bucket).upload(path, data, options)


def _signed_url(bucket: str, path: str, expires_in: int) -> str:
    response = get_supabase().storage.from_(bucket).create_signed_url(path, expires_in)
    url = response.get("signedURL")
    if not url:
        raise RuntimeError(f"Fichier introuvable dans le Storage : {path}")
    return url
